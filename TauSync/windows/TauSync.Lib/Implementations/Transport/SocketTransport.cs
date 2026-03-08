using System;
using System.Buffers;
using System.IO;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using TauSync.Core;
using TauSync.Interfaces;

namespace TauSync.Implementations.Transport
{
    /// <summary>
    /// TCP socket transport. Per spec: sends/receives raw TPack (8-byte header + payload).
    /// Performs TPack reassembly: buffers incoming bytes until a complete TPack (8-byte header + Length bytes payload)
    /// is available, then raises OnDataReceived once per full packet. This ensures ConnectionManager and above
    /// never see fragments (e.g. when TCP delivers partial data).
    /// </summary>
    public class SocketTransport : ITransport
    {
        private TcpClient? _tcpClient;
        private TcpListener? _tcpListener;
        private Stream? _stream;
        private string? _targetId;
        private bool _isConnected;
        private bool _disposed;
        private CancellationTokenSource? _receiveCts;
        private Task? _receiveTask;
        private Task? _acceptTask;
        private TaskCompletionSource? _connectionTcs;
        private readonly SemaphoreSlim _sendLock = new SemaphoreSlim(1, 1);

        // Reassembly buffer: accumulate bytes until we have a full TPack (8 + Length bytes)
        private readonly byte[] _headerBuffer = new byte[CoreConfig.TPackHeaderSize];
        private byte[]? _receiveBuffer;

        public static readonly int DefaultPort = CoreConfig.DefaultPort;

        public int Port { get; set; } = DefaultPort;

        public event EventHandler<byte[]>? OnDataReceived;

        /// <summary>
        /// Parameterless constructor for dependency injection (client or server mode set by Connect).
        /// </summary>
        public SocketTransport()
        {
        }

        /// <inheritdoc />
        public async Task Connect(string? targetId)
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(SocketTransport));

            if (_isConnected)
                Disconnect();

            if (string.IsNullOrWhiteSpace(targetId))
            {
                // Server mode: listen and wait for first client (internal; no public API for callers).
                StartListeningInternal();
                await WaitForConnectionInternalAsync().ConfigureAwait(false);
                return;
            }

            _targetId = targetId;
            _tcpClient = new TcpClient();
            await _tcpClient.ConnectAsync(targetId, Port).ConfigureAwait(false);
            _stream = _tcpClient.GetStream();
            _isConnected = true;
            _receiveCts = new CancellationTokenSource();
            _receiveTask = Task.Run(() => ReceiveLoopAsync(_receiveCts.Token));
        }

        /// <summary>
        /// Internal: start listening (server mode). Used only by <see cref="Connect"/> when targetId is null/empty.
        /// </summary>
        private void StartListeningInternal()
        {
            if (_tcpListener != null)
                return;

            _connectionTcs = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            _tcpListener = new TcpListener(System.Net.IPAddress.Any, Port);
            _tcpListener.Start();
            _receiveCts = new CancellationTokenSource();
            _acceptTask = Task.Run(() => AcceptLoopAsync(_receiveCts.Token));
        }

        /// <summary>
        /// Internal: wait for first client to connect. Used only by <see cref="Connect"/> in server mode.
        /// </summary>
        private Task WaitForConnectionInternalAsync()
        {
            if (_connectionTcs == null)
                throw new InvalidOperationException("StartListeningInternal must have been called.");
            return _connectionTcs.Task;
        }

        /// <inheritdoc />
        public async Task SendRaw(byte[] data)
        {
            if (data == null)
                throw new ArgumentNullException(nameof(data));
            if (_disposed)
                throw new ObjectDisposedException(nameof(SocketTransport));
            if (!_isConnected || _stream == null)
                throw new InvalidOperationException("Not connected.");

            await _sendLock.WaitAsync().ConfigureAwait(false);
            try
            {
                await _stream.WriteAsync(data, 0, data.Length).ConfigureAwait(false);
                await _stream.FlushAsync().ConfigureAwait(false);
            }
            finally
            {
                _sendLock.Release();
            }
        }

        /// <inheritdoc />
        public bool IsConnected()
        {
            return _isConnected && !_disposed && _tcpClient?.Connected == true;
        }

        public void Disconnect()
        {
            if (!_isConnected) return;
            _isConnected = false;
            _receiveCts?.Cancel();
            try { _receiveTask?.Wait(TimeSpan.FromSeconds(2)); } catch { }
            _stream?.Close();
            _tcpClient?.Close();
            _stream = null;
            _tcpClient = null;
            _targetId = null;
        }

        private async Task AcceptLoopAsync(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested && _tcpListener != null)
            {
                try
                {
                    _tcpClient = await _tcpListener.AcceptTcpClientAsync(ct).ConfigureAwait(false);
                    _stream = _tcpClient.GetStream();
                    _isConnected = true;
                    _receiveCts = new CancellationTokenSource();
                    _receiveTask = Task.Run(() => ReceiveLoopAsync(_receiveCts.Token));
                    _connectionTcs?.TrySetResult();
                    break;
                }
                catch (OperationCanceledException) { break; }
                catch (Exception) { break; }
            }
        }

        /// <summary>
        /// Read until we have 8 bytes, then read Length bytes; raise OnDataReceived with full TPack.
        /// </summary>
        private async Task ReceiveLoopAsync(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested && _isConnected && _stream != null)
            {
                try
                {
                    // Read header (8 bytes)
                    int headerRead = await ReadExactlyAsync(_stream, _headerBuffer, 0, CoreConfig.TPackHeaderSize, ct).ConfigureAwait(false);
                    if (headerRead != CoreConfig.TPackHeaderSize)
                        break;

                    int payloadLength = _headerBuffer[0] | (_headerBuffer[1] << 8) | (_headerBuffer[2] << 16) | (_headerBuffer[3] << 24);
                    if (payloadLength < 0)
                    {
                        break;
                    }

                    int totalPacketSize = CoreConfig.TPackHeaderSize + payloadLength;
                    if (_receiveBuffer == null || _receiveBuffer.Length < totalPacketSize)
                        _receiveBuffer = new byte[Math.Max(totalPacketSize, 65536)];
                    Buffer.BlockCopy(_headerBuffer, 0, _receiveBuffer, 0, CoreConfig.TPackHeaderSize);

                    if (payloadLength > 0)
                    {
                        int payloadRead = await ReadExactlyAsync(_stream, _receiveBuffer, CoreConfig.TPackHeaderSize, payloadLength, ct).ConfigureAwait(false);
                        if (payloadRead != payloadLength)
                            break;
                    }

                    byte[] packet = new byte[totalPacketSize];
                    Buffer.BlockCopy(_receiveBuffer, 0, packet, 0, totalPacketSize);
                    OnDataReceived?.Invoke(this, packet);
                }
                catch (OperationCanceledException) { break; }
                catch (Exception) { break; }
            }

            if (_isConnected)
                Disconnect();
        }

        private static async Task<int> ReadExactlyAsync(Stream stream, byte[] buffer, int offset, int count, CancellationToken ct)
        {
            int totalRead = 0;
            while (totalRead < count)
            {
                int r = await stream.ReadAsync(buffer, offset + totalRead, count - totalRead, ct).ConfigureAwait(false);
                if (r == 0) return totalRead;
                totalRead += r;
            }
            return totalRead;
        }

        public void Dispose()
        {
            if (_disposed) return;
            Disconnect();
            _tcpListener?.Stop();
            try { _acceptTask?.Wait(TimeSpan.FromSeconds(1)); } catch { }
            _receiveCts?.Dispose();
            _sendLock.Dispose();
            _disposed = true;
        }
    }
}

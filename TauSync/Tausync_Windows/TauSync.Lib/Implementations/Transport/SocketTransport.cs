using System;
using System.IO;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using TauSync.Core;
using TauSync.Implementations.Management;
using TauSync.Implementations.Protocol;
using TauSync.Interfaces;

namespace TauSync.Implementations.Transport
{
    /// <summary>
    /// TCP socket transport. Protocol-agnostic: reads frames via <see cref="IProtocolHandler"/> only.
    /// ReceiveLoopAsync and ReadExactlyAsync do not depend on TPack or any specific protocol.
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
        // for timeout
        private CancellationTokenSource? _timeoutCts;
        private Task? _receiveTask;
        private Task? _acceptTask;
        private TaskCompletionSource? _connectionTcs;
        private readonly SemaphoreSlim _sendLock = new SemaphoreSlim(1, 1);
        private readonly IProtocolHandler _protocolHandler;

        public static readonly int DefaultPort = CoreConfig.DefaultPort;

        public int Port { get; set; } = DefaultPort;

        /// <summary>When true, only server (listen); when false, only client (connect); when null, mode is determined by Connect(targetId).</summary>
        private bool _isServerMode;

        /// <summary>Whether this transport accepted a connection (server) rather than initiated one (client).</summary>
        public bool IsServerMode => _isServerMode;

        public event EventHandler<byte[]>? OnDataReceived;

        /// <summary>Uses the given protocol handler for framing; if null, uses default <see cref="ProtocolHandler"/>.</summary>
        public SocketTransport(IProtocolHandler? protocolHandler = null)
        {
            _protocolHandler = protocolHandler ?? new ProtocolHandler();
        }

        /// <inheritdoc />
        public async Task Connect(string? targetId, int? timeoutSeconds = null)
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(SocketTransport));

            if (_isConnected)
                Disconnect();

            bool wantServer = string.IsNullOrWhiteSpace(targetId);
            _isServerMode = wantServer;

            if (_isServerMode)
            {
                StartListeningInternal(timeoutSeconds);
                await WaitForConnectionInternalAsync().ConfigureAwait(false);
                return;
            }

            _targetId = targetId;
            await ConnectToServerWithRetryAsync(targetId!, timeoutSeconds).ConfigureAwait(false);
        }

        /// <summary>
        /// Connects to the server by awaiting a task that completes only when the connection succeeds.
        /// Retries are driven by a timer (no busy loop): the calling thread awaits once; a background
        /// loop runs TryConnectOnce after each delay until connected or disposed.
        /// </summary>
        private async Task ConnectToServerWithRetryAsync(string host, int? timeoutSeconds)
        {
            var connectedTcs = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            int delayMs = CoreConfig.ClientConnectRetryDelaySeconds * 1000;
            var tryLock = new SemaphoreSlim(1, 1);

            _timeoutCts = new CancellationTokenSource(GetTimeout(timeoutSeconds));

            _ = RunConnectRetryLoopAsync(host, connectedTcs, delayMs, tryLock, _timeoutCts.Token);
            await connectedTcs.Task.ConfigureAwait(false);
        }

        private async Task RunConnectRetryLoopAsync(string host, TaskCompletionSource connectedTcs, int delayMs, SemaphoreSlim tryLock, CancellationToken ct)
        {
            while (!connectedTcs.Task.IsCompleted && !_disposed && !ct.IsCancellationRequested)
            {
                // if (_disposed)
                // {
                // connectedTcs.TrySetException(new ObjectDisposedException(nameof(SocketTransport)));
                // break;
                // }

                try
                {
                    await TryConnectOnceAsync(host, connectedTcs, tryLock, ct).ConfigureAwait(false);
                    await Task.Delay(delayMs, ct).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    if (_timeoutCts != null && _timeoutCts.IsCancellationRequested)
                    {
                        connectedTcs.TrySetException(new TimeoutException("Failed to connect within the timeout period."));
                    }
                    break;
                }


            }
            if (ct.IsCancellationRequested && !connectedTcs.Task.IsCompleted)
            {
                connectedTcs.TrySetException(new TimeoutException("Failed to connect within the timeout period."));
            }

        }


        // for easy conversion. if timeoutSeconds is null, returns infinite timespan; otherwise, returns the corresponding timespan.
        private static TimeSpan GetTimeout(int? timeoutSeconds)
        {
            return timeoutSeconds.HasValue ? TimeSpan.FromSeconds(timeoutSeconds.Value) : Timeout.InfiniteTimeSpan;
        }


        private async Task TryConnectOnceAsync(
            string host, TaskCompletionSource connectedTcs, SemaphoreSlim tryLock, CancellationToken ct)
        {
            if (_disposed)
            {
                connectedTcs.TrySetException(new ObjectDisposedException(nameof(SocketTransport)));
                return;
            }

            try
            {
                await tryLock.WaitAsync(ct).ConfigureAwait(false);
                if (connectedTcs.Task.IsCompleted || _disposed)
                    return;

                var client = new TcpClient();
                try
                {
                    await client.ConnectAsync(host, Port).WaitAsync(ct).ConfigureAwait(false);
                    if (connectedTcs.Task.IsCompleted || _disposed)
                    {
                        client.Close();
                        return;
                    }

                    _tcpClient = client;
                    _stream = client.GetStream();
                    _isConnected = true;
                    _receiveCts = new CancellationTokenSource();
                    _receiveTask = Task.Run(() => ReceiveLoopAsync(_receiveCts.Token));
                    connectedTcs.TrySetResult();
                }
                catch (SocketException)
                {
                    client.Close();
                }
                catch (OperationCanceledException)
                {
                    client.Close();
                    throw;
                }
                catch (Exception ex)
                {
                    client.Close();
                    connectedTcs.TrySetException(ex);
                }
            }
            finally
            {
                tryLock.Release();
            }
        }

        /// <summary>
        /// Internal: start listening (server mode). Used only by <see cref="Connect"/> when targetId is null/empty.
        /// </summary>
        private void StartListeningInternal(int? timeoutSeconds = null)
        {
            if (_tcpListener != null)
                return;

            _connectionTcs = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            _tcpListener = new TcpListener(System.Net.IPAddress.Any, Port);
            _tcpListener.Start();

            _receiveCts = new CancellationTokenSource();

            _timeoutCts = new CancellationTokenSource(GetTimeout(timeoutSeconds));

            var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(_receiveCts.Token, _timeoutCts.Token);
            _acceptTask = Task.Run(() => AcceptLoopAsync(linkedCts.Token));
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
           _receiveCts?.Cancel();
            try { _receiveTask?.Wait(TimeSpan.FromSeconds(2)); } catch { }
                try { _acceptTask?.Wait(TimeSpan.FromSeconds(1)); } catch { }
              _tcpListener?.Stop();
             _stream?.Close();
            _tcpClient?.Close();

             _tcpListener = null;
            _stream = null;
             _tcpClient = null;
             _isConnected = false;
            _receiveCts = null;
             _timeoutCts = null;
            _receiveTask = null;
            _acceptTask = null;
            _connectionTcs = null;
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
                catch (OperationCanceledException)
                {
                    _tcpClient?.Close();
                    _tcpClient = null;
                    _tcpListener?.Stop();
                    _tcpListener = null;
                    if (_timeoutCts != null && _timeoutCts.IsCancellationRequested)
                    {
                        _connectionTcs?.TrySetException(new TimeoutException("No client connected within the timeout period."));
                    }
                    break;
                }
                catch (Exception) { break; }
            }
        }

        /// <summary>
        /// Read exactly <paramref name="count"/> bytes from the stream into the buffer.
        /// Protocol-agnostic: just "read N bytes".
        /// </summary>
        /// <returns>Number of bytes read (less than count only on EOF).</returns>
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

        /// <summary>
        /// Receive loop: read one frame at a time using only <see cref="IProtocolHandler"/> (no TPack/constants here).
        /// </summary>
        private async Task ReceiveLoopAsync(CancellationToken ct)
        {
            int headerSize = _protocolHandler.GetHeaderSize();
            byte[] headerBuffer = new byte[headerSize];

            while (!ct.IsCancellationRequested && _isConnected && _stream != null)
            {
                try
                {
                    var result = await TryReadNextFrameAsync(ct, headerSize, headerBuffer).ConfigureAwait(false);
                    if (!result.success)
                        break;

                    DispatchFrame(result.targetId, result.payload, result.flags, result.rawFrame);
                }
                catch (OperationCanceledException) { break; }
                catch (Exception) { break; }
            }

            if (_isConnected)
                Disconnect();
        }

        private async Task<ReadFrameResult> TryReadNextFrameAsync(CancellationToken ct, int headerSize, byte[] headerBuffer)
        {
            int headerRead = await ReadExactlyAsync(_stream!, headerBuffer, 0, headerSize, ct).ConfigureAwait(false);
            if (headerRead != headerSize)
                return ReadFrameResult.Failed;

            int payloadLength = _protocolHandler.GetPayloadLength(headerBuffer);
            if (payloadLength < 0)
                return ReadFrameResult.Failed;

            int totalFrameSize = headerSize + payloadLength;
            byte[] frame = new byte[totalFrameSize];
            Buffer.BlockCopy(headerBuffer, 0, frame, 0, headerSize);

            if (payloadLength > 0)
            {
                int payloadRead = await ReadExactlyAsync(_stream!, frame, headerSize, payloadLength, ct).ConfigureAwait(false);
                if (payloadRead != payloadLength)
                    return ReadFrameResult.Failed;
            }

            (int targetId, byte[] payload, byte flags) = _protocolHandler.ParseFrame(frame);
            return ReadFrameResult.Success(targetId, payload, flags, frame);
        }

        private void DispatchFrame(int targetId, byte[] payload, byte flags, byte[] rawFrame)
        {
            if (_protocolHandler.IsControlFrame(targetId, flags))
            {
                bool handled = ConnectionContext.Instance.Dispatch(targetId, payload, flags);
                if (!handled)
                    OnDataReceived?.Invoke(this, rawFrame);
                return;
            }

            ConnectionContext.Instance.Dispatch(targetId, payload, flags);
        }

        private readonly struct ReadFrameResult
        {
            public static ReadFrameResult Failed => new ReadFrameResult(false, 0, Array.Empty<byte>(), 0, Array.Empty<byte>());

            public static ReadFrameResult Success(int targetId, byte[] payload, byte flags, byte[] rawFrame) =>
                new ReadFrameResult(true, targetId, payload, flags, rawFrame);

            public bool success { get; }
            public int targetId { get; }
            public byte[] payload { get; }
            public byte flags { get; }
            public byte[] rawFrame { get; }

            private ReadFrameResult(bool success, int targetId, byte[] payload, byte flags, byte[] rawFrame)
            {
                this.success = success;
                this.targetId = targetId;
                this.payload = payload;
                this.flags = flags;
                this.rawFrame = rawFrame;
            }
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

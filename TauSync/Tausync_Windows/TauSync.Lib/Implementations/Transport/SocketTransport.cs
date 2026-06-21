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

        /// <summary>True only while an explicit <see cref="Disconnect"/> is tearing the transport down. Distinguishes a deliberate close (ends the session) from an unexpected drop (triggers reconnect).</summary>
        private volatile bool _intentionalClose;

        /// <summary>True once this transport has been counted in <see cref="ConnectionContext"/>, so the matching disconnect decrements exactly once.</summary>
        private bool _counted;

        /// <summary>Cancels the background reconnect loop when the app explicitly disconnects.</summary>
        private CancellationTokenSource? _reconnectCts;

        /// <summary>
        /// Completed while a live connection exists; reset to an incomplete state during a
        /// reconnect so a send issued mid-drop waits for the link to come back instead of
        /// failing. <see cref="SendRaw"/> awaits this before writing.
        /// </summary>
        private volatile TaskCompletionSource _sendGate =
            new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

        public static readonly int DefaultPort = CoreConfig.DefaultPort;

        public int Port { get; set; } = DefaultPort;

        /// <summary>When true, only server (listen); when false, only client (connect); when null, mode is determined by Connect(targetId).</summary>
        private bool _isServerMode;

        /// <summary>Whether this transport accepted a connection (server) rather than initiated one (client).</summary>
        public bool IsServerMode => _isServerMode;

        /// <summary>
        /// UTC ticks of the last frame sent or received. The hybrid coordinator reads this to decide
        /// when the Wi-Fi link has been idle long enough to disconnect. Initialised to "now" so a
        /// freshly connected link is not immediately considered idle.
        /// </summary>
        private long _lastActivityTicks = DateTime.UtcNow.Ticks;

        /// <summary>UTC ticks of the last send or receive on this transport (see <see cref="_lastActivityTicks"/>).</summary>
        public long LastActivityTicks => Volatile.Read(ref _lastActivityTicks);

        private void MarkActivity() => Volatile.Write(ref _lastActivityTicks, DateTime.UtcNow.Ticks);

        public event EventHandler<byte[]>? OnDataReceived;

        /// <inheritdoc />
        public TransportKind TransportType => TransportKind.WiFi;

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

            // Re-arm for a fresh session: a prior Disconnect() left _intentionalClose set,
            // and the gate must start incomplete until this connection succeeds.
            _intentionalClose = false;
            _sendGate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

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

            _timeoutCts?.Dispose();
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
                    MarkInitialConnection();
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

            _timeoutCts?.Dispose();
            _timeoutCts = new CancellationTokenSource(GetTimeout(timeoutSeconds));

            var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(_receiveCts.Token, _timeoutCts.Token);
            _acceptTask = Task.Run(async () =>
            {
                // Own the linked CTS for the lifetime of the accept loop so it is always disposed.
                using (linkedCts)
                {
                    await AcceptLoopAsync(linkedCts.Token).ConfigureAwait(false);
                }
            });
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

            // Block briefly if an unexpected drop is being healed, so a write issued during
            // the reconnect window resumes on the new link instead of failing.
            await WaitForConnectionAsync().ConfigureAwait(false);
            if (!_isConnected || _stream == null)
                throw new InvalidOperationException("Not connected.");

            await _sendLock.WaitAsync().ConfigureAwait(false);
            try
            {
                await _stream.WriteAsync(data, 0, data.Length).ConfigureAwait(false);
                await _stream.FlushAsync().ConfigureAwait(false);
                MarkActivity();
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

        /// <summary>
        /// Marks this transport connected exactly once and counts it in
        /// <see cref="ConnectionContext"/>. Called only on the FIRST successful connect —
        /// reconnects after a drop reuse the same count, so the session is never double-counted.
        /// </summary>
        private void MarkInitialConnection()
        {
            if (!_counted)
            {
                _counted = true;
                ConnectionContext.Instance.NotifyTransportConnected();
            }
            _sendGate.TrySetResult();
        }

        /// <summary>
        /// Explicit, app-initiated teardown. Ends the session for this transport: stops any
        /// reconnect attempt and notifies <see cref="ConnectionContext"/>, which aborts the
        /// open channels and resets state only if this was the last live transport.
        /// </summary>
        public void Disconnect()
        {
            if (_intentionalClose) return;
            _intentionalClose = true;
            _isConnected = false;

            _reconnectCts?.Cancel();
            _receiveCts?.Cancel();

            // Release any sender parked on the gate; it will see _isConnected == false and throw.
            _sendGate.TrySetResult();

            try { _receiveTask?.Wait(TimeSpan.FromSeconds(2)); } catch { }
            try { _acceptTask?.Wait(TimeSpan.FromSeconds(1)); } catch { }
            _tcpListener?.Stop();
            _stream?.Close();
            _tcpClient?.Close();

            // Decrement the transport count exactly once. Channels are aborted (synthetic FIN
            // so blocked Read() calls return EOF) and state reset only when the count hits zero.
            if (_counted)
            {
                _counted = false;
                ConnectionContext.Instance.NotifyTransportDisconnected();
            }

            _tcpListener = null;
            _stream = null;
            _tcpClient = null;
            _receiveCts?.Dispose();
            _receiveCts = null;
            _timeoutCts?.Dispose();
            _timeoutCts = null;
            _reconnectCts?.Dispose();
            _reconnectCts = null;
            _receiveTask = null;
            _acceptTask = null;
            _connectionTcs = null;
        }

        /// <summary>
        /// Handles the receive loop exiting on a broken link. An explicit disconnect ends the
        /// session; an unexpected drop instead tears down only the dead socket — keeping the
        /// channels, handlers, and transport count intact — and starts reconnecting so the
        /// session resumes transparently.
        /// </summary>
        private void HandleConnectionDropped()
        {
            if (_intentionalClose || _disposed) return;
            if (!_isConnected) return;
            _isConnected = false;

            // Fresh incomplete gate so sends block until the link is back.
            _sendGate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

            try { _stream?.Close(); } catch { }
            try { _tcpClient?.Close(); } catch { }
            _stream = null;
            _tcpClient = null;

            StartReconnectLoop();
        }

        private void StartReconnectLoop()
        {
            _reconnectCts?.Dispose();
            _reconnectCts = new CancellationTokenSource();
            CancellationToken ct = _reconnectCts.Token;
            _ = Task.Run(() => ReconnectLoopAsync(ct));
        }

        /// <summary>
        /// Retries the connection with exponential back-off until it succeeds or an explicit
        /// disconnect cancels it. On success it restarts the receive loop and opens the send
        /// gate, all on the same channel handlers — the layers above never see the gap.
        /// </summary>
        private async Task ReconnectLoopAsync(CancellationToken ct)
        {
            int delayMs = CoreConfig.ReconnectInitialDelayMs;
            while (!ct.IsCancellationRequested && !_disposed && !_intentionalClose)
            {
                try
                {
                    bool reconnected = _isServerMode
                        ? await TryReListenAsync(ct).ConfigureAwait(false)
                        : await TryReconnectClientAsync(ct).ConfigureAwait(false);

                    if (reconnected)
                    {
                        _isConnected = true;
                        _receiveCts = new CancellationTokenSource();
                        _receiveTask = Task.Run(() => ReceiveLoopAsync(_receiveCts.Token));
                        _sendGate.TrySetResult();
                        return;
                    }
                }
                catch (OperationCanceledException) { return; }
                catch { /* transient failure — fall through to back-off and retry */ }

                try { await Task.Delay(delayMs, ct).ConfigureAwait(false); }
                catch (OperationCanceledException) { return; }
                delayMs = Math.Min(delayMs * 2, CoreConfig.ReconnectMaxDelayMs);
            }
        }

        private async Task<bool> TryReconnectClientAsync(CancellationToken ct)
        {
            var client = new TcpClient();
            try
            {
                await client.ConnectAsync(_targetId!, Port).WaitAsync(ct).ConfigureAwait(false);
                _tcpClient = client;
                _stream = client.GetStream();
                return true;
            }
            catch (OperationCanceledException)
            {
                client.Close();
                throw;
            }
            catch
            {
                client.Close();
                return false;
            }
        }

        private async Task<bool> TryReListenAsync(CancellationToken ct)
        {
            // The listener opened for the initial accept stays bound for the transport's
            // lifetime, so reuse it. Re-binding a fresh listener to the same port would
            // fail with "address already in use".
            if (_tcpListener == null)
            {
                _tcpListener = new TcpListener(System.Net.IPAddress.Any, Port);
                _tcpListener.Start();
            }

            try
            {
                TcpClient client = await _tcpListener.AcceptTcpClientAsync(ct).ConfigureAwait(false);
                _tcpClient = client;
                _stream = client.GetStream();
                return true;
            }
            catch (OperationCanceledException) { throw; }
            catch { return false; }
        }

        private async Task WaitForConnectionAsync()
        {
            Task gate = _sendGate.Task;
            if (gate.IsCompleted) return;
            await gate.WaitAsync(TimeSpan.FromMilliseconds(CoreConfig.SendReconnectWaitMs)).ConfigureAwait(false);
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
                    MarkInitialConnection();
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
                catch (Exception ex)
                {
                    // The listener died for a non-cancellation reason. Clean up the listener and
                    // fault the connection TCS: leaving _tcpListener non-null made the next
                    // Connect("") return early from StartListeningInternal (never arming the new
                    // timeout) and await this stale TCS forever.
                    _tcpClient?.Close();
                    _tcpClient = null;
                    _tcpListener?.Stop();
                    _tcpListener = null;
                    _connectionTcs?.TrySetException(ex);
                    break;
                }
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

                    MarkActivity();
                    DispatchFrame(result.targetId, result.payload, result.flags, result.rawFrame);
                }
                catch (OperationCanceledException) { break; }
                catch (Exception) { break; }
            }

            HandleConnectionDropped();
        }

        private async Task<ReadFrameResult> TryReadNextFrameAsync(CancellationToken ct, int headerSize, byte[] headerBuffer)
        {
            int headerRead = await ReadExactlyAsync(_stream!, headerBuffer, 0, headerSize, ct).ConfigureAwait(false);
            if (headerRead != headerSize)
                return ReadFrameResult.Failed;

            int payloadLength = _protocolHandler.GetPayloadLength(headerBuffer);
            if (payloadLength < 0 || payloadLength > CoreConfig.MaxPayloadSize)
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

using System;
using System.Threading;
using System.Threading.Tasks;
using TauSync.Core;
using TauSync.Implementations.Management;
using TauSync.Implementations.Protocol;
using TauSync.Interfaces;
using Windows.Devices.Bluetooth.Rfcomm;
using Windows.Networking.Sockets;
using Windows.Storage.Streams;

namespace TauSync.Implementations.Transport
{
    /// <summary>
    /// Bluetooth Classic (RFCOMM) transport. Protocol-agnostic: reads frames via
    /// <see cref="IProtocolHandler"/> only, exactly like <see cref="SocketTransport"/>.
    /// The RFCOMM byte stream is a drop-in replacement for the TCP stream, so the framing,
    /// dispatch, and send-lock logic are identical to the Wi-Fi transport.
    ///
    /// <para>Windows always acts as the RFCOMM <b>server</b>: it advertises the service over
    /// SDP and accepts one incoming connection. Client mode is not supported here — Android
    /// is always the RFCOMM client.</para>
    /// </summary>
    public class BluetoothTransport : ITransport
    {
        private RfcommServiceProvider? _serviceProvider;
        private StreamSocketListener? _listener;
        private StreamSocket? _socket;
        private DataWriter? _writer;
        private DataReader? _reader;
        private CancellationTokenSource? _receiveCts;
        private CancellationTokenSource? _timeoutCts;
        private Task? _receiveTask;
        private TaskCompletionSource? _connectionTcs;
        private readonly SemaphoreSlim _sendLock = new SemaphoreSlim(1, 1);
        private readonly IProtocolHandler _protocolHandler;
        private volatile bool _isConnected;
        private bool _disposed;

        /// <summary>
        /// Serializes every transition of the connection state machine — <see cref="Connect"/>,
        /// <see cref="Disconnect"/>, <see cref="OnConnectionReceived"/>, and
        /// <see cref="HandleConnectionDropped"/>. Without it the background reconnect loop could
        /// start (and keep re-advertising) after an explicit disconnect cancelled the old token, then
        /// race a fresh listen for ownership of the single RFCOMM service — the "phantom connect" where
        /// <see cref="Connect"/> returns with no live peer. Never held across a blocking wait.
        /// </summary>
        private readonly object _stateLock = new object();

        /// <summary>True only while an explicit <see cref="Disconnect"/> is tearing the transport down. Distinguishes a deliberate close (ends the session) from an unexpected drop (which converges to a clean reset).</summary>
        private volatile bool _intentionalClose;

        /// <summary>True once this transport has been counted in <see cref="ConnectionContext"/>, so the matching disconnect decrements exactly once.</summary>
        private bool _counted;

        /// <summary>
        /// Completed while a live connection exists; reset to an incomplete state on an unexpected
        /// drop so a send issued during the drop fails fast instead of writing into a dead socket.
        /// <see cref="SendRaw"/> awaits this before writing.
        /// </summary>
        private volatile TaskCompletionSource _sendGate =
            new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

        public event EventHandler<byte[]>? OnDataReceived;

        /// <inheritdoc />
        public TransportKind TransportType => TransportKind.Bluetooth;

        /// <inheritdoc />
        /// <remarks>Windows always acts as the RFCOMM server, so this is always true.</remarks>
        public bool IsServerMode => true;

        /// <summary>Uses the given protocol handler for framing; if null, uses default <see cref="ProtocolHandler"/>.</summary>
        public BluetoothTransport(IProtocolHandler? protocolHandler = null)
        {
            _protocolHandler = protocolHandler ?? new ProtocolHandler();
        }

        /// <summary>
        /// Starts the RFCOMM listener (server mode) and waits for the first incoming connection.
        /// A non-empty <paramref name="targetId"/> is rejected: Windows is always the BT server.
        /// </summary>
        public async Task Connect(string? targetId, int? timeoutSeconds = null)
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(BluetoothTransport));
            if (!string.IsNullOrWhiteSpace(targetId))
                throw new NotSupportedException(
                    "BluetoothTransport operates in RFCOMM server mode only; pass null/empty targetId.");
            if (_isConnected)
                Disconnect();

            lock (_stateLock)
            {
                // Stop any stale advertiser so this fresh listen owns the single RFCOMM service
                // exclusively, then re-arm: a prior Disconnect()/drop left _intentionalClose set, and
                // the gate must start incomplete until this connection succeeds.
                StopAdvertising();
                _intentionalClose = false;
                _sendGate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            }

            await StartListeningAsync(timeoutSeconds).ConfigureAwait(false);
            await _connectionTcs!.Task.ConfigureAwait(false);
        }

        private async Task StartListeningAsync(int? timeoutSeconds)
        {
            _connectionTcs = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

            _serviceProvider = await RfcommServiceProvider
                .CreateAsync(RfcommServiceId.FromUuid(CoreConfig.RfcommServiceUuid))
                .AsTask().ConfigureAwait(false);

            _listener = new StreamSocketListener();
            _listener.ConnectionReceived += OnConnectionReceived;
            await _listener.BindServiceNameAsync(
                    _serviceProvider.ServiceId.AsString(),
                    SocketProtectionLevel.BluetoothEncryptionAllowNullAuthentication)
                .AsTask().ConfigureAwait(false);

            // true = publish the SDP record so the Android client can resolve the RFCOMM
            // channel number from RFCOMM_SERVICE_UUID.
            _serviceProvider.StartAdvertising(_listener, true);

            ArmConnectionTimeout(timeoutSeconds);
        }

        private void ArmConnectionTimeout(int? timeoutSeconds)
        {
            if (timeoutSeconds is not int seconds)
                return;
            _timeoutCts?.Dispose();
            _timeoutCts = new CancellationTokenSource(TimeSpan.FromSeconds(seconds));
            _timeoutCts.Token.Register(() =>
            {
                bool timedOut = _connectionTcs?.TrySetException(
                    new TimeoutException("No Bluetooth client connected within the timeout period.")) == true;
                if (!timedOut)
                    return;

                // The listen window is over — stop advertising so a peer cannot be adopted by a
                // listener nobody is handshaking on. Without this the stale advertiser lives on
                // until the next Connect(), silently accepting (then orphaning) incoming peers.
                lock (_stateLock)
                {
                    if (!_isConnected && !_disposed)
                        StopAdvertising();
                }
            });
        }

        private void OnConnectionReceived(
            StreamSocketListener sender, StreamSocketListenerConnectionReceivedEventArgs args)
        {
            lock (_stateLock)
            {
                // Ignore a connection that arrives after an explicit Disconnect, after disposal, or
                // from a listener a newer Connect has already superseded. Adopting it would resurrect a
                // session the app has torn down, or let two listeners fight over _socket/_connectionTcs.
                if (_intentionalClose || _disposed || !ReferenceEquals(sender, _listener))
                {
                    try { args.Socket.Dispose(); } catch { }
                    return;
                }

                _socket = args.Socket;
                _writer = new DataWriter(_socket.OutputStream);
                _reader = new DataReader(_socket.InputStream) { InputStreamOptions = InputStreamOptions.None };
                _isConnected = true;

                // One connection only: stop advertising/listening once a peer attaches.
                StopAdvertising();

                _receiveCts = new CancellationTokenSource();
                _receiveTask = Task.Run(() => ReceiveLoopAsync(_receiveCts.Token));

                // Counts the transport once and opens the send gate. Fires for both the initial
                // connection and every successful re-advertise after an unexpected drop.
                MarkInitialConnection();
                _connectionTcs?.TrySetResult();
            }
        }

        /// <inheritdoc />
        public async Task SendRaw(byte[] data)
        {
            if (data == null)
                throw new ArgumentNullException(nameof(data));
            if (_disposed)
                throw new ObjectDisposedException(nameof(BluetoothTransport));

            // Block briefly if an unexpected drop is being healed, so a write issued during
            // the reconnect window resumes on the new link instead of failing.
            await WaitForConnectionAsync().ConfigureAwait(false);
            if (!_isConnected || _writer == null)
                throw new InvalidOperationException("Not connected.");

            await _sendLock.WaitAsync().ConfigureAwait(false);
            try
            {
                _writer.WriteBytes(data);
                await _writer.StoreAsync().AsTask().ConfigureAwait(false);
            }
            finally
            {
                _sendLock.Release();
            }
        }

        /// <inheritdoc />
        public bool IsConnected()
        {
            return _isConnected && !_disposed && _socket != null;
        }

        /// <summary>
        /// Marks this transport connected exactly once and counts it in
        /// <see cref="ConnectionContext"/>. Called only on the FIRST successful connection —
        /// re-advertises after a drop reuse the same count, so the session is never double-counted.
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
            Task? receiveTask;
            lock (_stateLock)
            {
                if (_intentionalClose) return;
                _intentionalClose = true;
                _isConnected = false;

                // Cancel the receive loop while holding the lock. Because HandleConnectionDropped also
                // takes the lock and re-checks _intentionalClose, a receive loop exiting right now can
                // no longer race this teardown.
                _receiveCts?.Cancel();

                // Release any sender parked on the gate; it will see _isConnected == false and throw.
                _sendGate.TrySetResult();

                receiveTask = _receiveTask;
            }

            // Wait for the receive loop OUTSIDE the lock — it calls HandleConnectionDropped on exit,
            // which needs the lock. Holding it here would deadlock.
            try { receiveTask?.Wait(TimeSpan.FromSeconds(2)); } catch { }

            lock (_stateLock)
            {
                StopAdvertising();
                DetachStreams();
                _socket?.Dispose();

                // Decrement the transport count exactly once. Channels are aborted (synthetic FIN
                // so blocked Read() calls return EOF) and state reset only when the count hits zero.
                if (_counted)
                {
                    _counted = false;
                    ConnectionContext.Instance.NotifyTransportDisconnected();
                }

                _socket = null;
                _receiveCts?.Dispose();
                _receiveCts = null;
                _timeoutCts?.Dispose();
                _timeoutCts = null;
                _receiveTask = null;
                _connectionTcs = null;
            }
        }

        /// <summary>
        /// Handles the receive loop exiting on a broken RFCOMM link (the peer vanished, moved out of
        /// range, or its own stack reset). Unlike Wi-Fi, the Bluetooth primary does <b>not</b> silently
        /// reconnect: that is incompatible with the per-session ECDH key exchange and the connection
        /// approval, both of which the peer re-runs from scratch on every reconnect. A transport-level
        /// "resume" would adopt the peer's fresh handshake into the old (already-encrypted) session, so
        /// the new KEY_EXCHANGE is ignored and the link can never re-establish — the phone loops on BLE
        /// discovery. Instead we converge to a clean disconnected state: stop advertising and notify the
        /// context, which (when this was the last live transport) aborts the channels and resets the
        /// session — clearing the derived key and routing. The app then re-listens, so the peer's
        /// reconnect reaches a freshly-advertising PC and runs a brand-new handshake.
        /// </summary>
        private void HandleConnectionDropped()
        {
            bool notifyDisconnected = false;
            lock (_stateLock)
            {
                // Re-check under the lock: an explicit Disconnect may have just set _intentionalClose
                // and is already doing this teardown — don't double it.
                if (_intentionalClose || _disposed) return;
                if (!_isConnected) return;
                _isConnected = false;

                // Fresh incomplete gate so a send issued during the drop fails fast (it will time out
                // waiting and throw) instead of writing into a dead socket.
                _sendGate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

                DetachStreams();
                try { _socket?.Dispose(); } catch { }
                _socket = null;

                // Stop advertising the now-dead session's RFCOMM service. The app's fresh
                // connect re-advertises a clean one.
                StopAdvertising();

                if (_counted)
                {
                    _counted = false;
                    notifyDisconnected = true;
                }
            }

            // Notify OUTSIDE the lock: NotifyTransportDisconnected may abort channels and Reset() the
            // singleton (when the count hits zero), which must not run under this transport's lock.
            if (notifyDisconnected)
                ConnectionContext.Instance.NotifyTransportDisconnected();
        }

        private async Task WaitForConnectionAsync()
        {
            Task gate = _sendGate.Task;
            if (gate.IsCompleted) return;
            await gate.WaitAsync(TimeSpan.FromMilliseconds(CoreConfig.SendReconnectWaitMs)).ConfigureAwait(false);
        }

        private void StopAdvertising()
        {
            try { _serviceProvider?.StopAdvertising(); } catch { }
            if (_listener != null)
                _listener.ConnectionReceived -= OnConnectionReceived;
            _listener?.Dispose();
            _listener = null;
            _serviceProvider = null;
        }

        private void DetachStreams()
        {
            try { _writer?.DetachStream(); } catch { }
            try { _reader?.DetachStream(); } catch { }
            _writer?.Dispose();
            _reader?.Dispose();
            _writer = null;
            _reader = null;
        }

        private async Task ReceiveLoopAsync(CancellationToken ct)
        {
            int headerSize = _protocolHandler.GetHeaderSize();
            byte[] headerBuffer = new byte[headerSize];

            while (!ct.IsCancellationRequested && _isConnected && _reader != null)
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

            HandleConnectionDropped();
        }

        private async Task<ReadFrameResult> TryReadNextFrameAsync(CancellationToken ct, int headerSize, byte[] headerBuffer)
        {
            uint headerLoaded = await _reader!.LoadAsync((uint)headerSize).AsTask(ct).ConfigureAwait(false);
            if (headerLoaded != headerSize)
                return ReadFrameResult.Failed;
            _reader.ReadBytes(headerBuffer);

            int payloadLength = _protocolHandler.GetPayloadLength(headerBuffer);
            if (payloadLength < 0 || payloadLength > CoreConfig.MaxPayloadSize)
                return ReadFrameResult.Failed;

            int totalFrameSize = headerSize + payloadLength;
            byte[] frame = new byte[totalFrameSize];
            System.Buffer.BlockCopy(headerBuffer, 0, frame, 0, headerSize);

            if (payloadLength > 0)
            {
                uint payloadLoaded = await _reader.LoadAsync((uint)payloadLength).AsTask(ct).ConfigureAwait(false);
                if (payloadLoaded != payloadLength)
                    return ReadFrameResult.Failed;
                byte[] payloadBytes = new byte[payloadLength];
                _reader.ReadBytes(payloadBytes);
                System.Buffer.BlockCopy(payloadBytes, 0, frame, headerSize, payloadLength);
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
            _sendLock.Dispose();
            _disposed = true;
        }
    }
}

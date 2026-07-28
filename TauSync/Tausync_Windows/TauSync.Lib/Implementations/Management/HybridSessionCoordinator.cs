using System;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using TauSync.Core;
using TauSync.Implementations.Transport;
using TauSync.Implementations.Util;
using TauSync.Interfaces;
using TauSync.Models;

namespace TauSync.Implementations.Management
{
    /// <summary>
    /// Owns the Bluetooth↔Wi-Fi session for a hybrid <see cref="ConnectionManager"/>. Bluetooth is the
    /// always-on primary link carrying control traffic and small payloads; Wi-Fi is brought up lazily
    /// the first time a large payload needs it and torn down again after it sits idle.
    ///
    /// <para>Flow (see Bluetooth_Transport_Plan.md §2.1):
    /// after BT connects both sides exchange BT_MAGIC and the server mints a session token. When a
    /// large payload is queued, the side that needs Wi-Fi asks for it (client → WIFI_CONNECT_REQ; the
    /// server starts its TCP listener and replies WIFI_CONNECT_READY with the token + address); the
    /// client connects TCP and sends SESSION_JOIN; the server verifies the token and replies
    /// SESSION_JOIN_ACK. The Bluetooth role fixes the Wi-Fi role: BT server = Wi-Fi server.</para>
    ///
    /// <para>The coordinator never owns the channel routing maps — those live in the shared
    /// <see cref="ConnectionContext"/> singleton, so a channel works over whichever transport carried
    /// its frames.</para>
    /// </summary>
    internal sealed class HybridSessionCoordinator
    {
        private readonly ITransport _bluetooth;     // primary: control + small data, always connected
        private readonly SocketTransport _wifi;     // secondary: large data only, lazy
        private readonly IProtocolHandler _protocol;

        /// <summary>Guards every transition of the Wi-Fi state machine (_wifiUp / _wifiReady / _wifiActivating).</summary>
        private readonly object _wifiLock = new object();

        private volatile bool _isServer;
        private volatile bool _disposed;

        /// <summary>The peer's friendly Bluetooth name from its BT_MAGIC, shown in the approval prompt.</summary>
        private volatile string? _peerDeviceName;

        /// <summary>
        /// Optional gate run on the server right after the peer's BT_MAGIC arrives and before the
        /// session is completed: given the peer's device name, returns true to accept or false to
        /// reject. Null (the default) accepts every connection, so behaviour is unchanged unless a
        /// caller opts in.
        /// </summary>
        public Func<string?, bool>? ApprovalCallback { get; set; }

        /// <summary>Completed when the peer's BT_MAGIC arrives, unblocking <see cref="StartBtSessionAsync"/>.</summary>
        private TaskCompletionSource _peerMagicReceived =
            new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

        /// <summary>Completed when the client echoes SESSION_CONFIRM after receiving our BT_MAGIC, proving
        /// the Bluetooth link is still live at handshake end and not a half-open socket the phone left
        /// during a slow approval.</summary>
        private TaskCompletionSource _confirmReceived =
            new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

        /// <summary>Completed when Wi-Fi is usable for sending (server: SESSION_JOIN verified; client: ACK received).</summary>
        private TaskCompletionSource _wifiReady =
            new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

        private bool _wifiUp;
        private bool _wifiActivating;
        private Timer? _idleTimer;

        public HybridSessionCoordinator(ITransport bluetooth, SocketTransport wifi, IProtocolHandler protocol)
        {
            _bluetooth = bluetooth ?? throw new ArgumentNullException(nameof(bluetooth));
            _wifi = wifi ?? throw new ArgumentNullException(nameof(wifi));
            _protocol = protocol ?? throw new ArgumentNullException(nameof(protocol));
        }

        /// <summary>
        /// Runs the BT_MAGIC exchange after the Bluetooth link is up: both sides send their magic and
        /// wait for the peer's, then the server mints the session token. Must be called once, right
        /// after the Bluetooth transport connects.
        /// </summary>
        public async Task StartBtSessionAsync()
        {
            _isServer = _bluetooth.IsServerMode;
            _peerMagicReceived = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            _confirmReceived = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

            // BT_MAGIC carries our own Wi-Fi IP so the peer can reach us over Wi-Fi (or just display
            // the address) without anyone typing it in: the Bluetooth link discovers it for them.
            var magic = NewMessage(SessionControlMessage.TypeBtMagic);
            magic.WifiHost = NetworkUtils.GetLocalWifiIpAddress();
            magic.WifiPort = CoreConfig.DefaultPort;
            magic.DeviceName = Environment.MachineName;

            var approve = ApprovalCallback;
            if (_isServer && approve != null)
            {
                // Gated server: wait for the client's magic first so we know who is connecting, run the
                // approval, and only then reveal our magic. Withholding our magic is what keeps the
                // client from completing its connect — so a declined client never sees itself connected.
                await _peerMagicReceived.Task
                    .WaitAsync(TimeSpan.FromMilliseconds(CoreConfig.BtHandshakeTimeoutMs))
                    .ConfigureAwait(false);

                // Tell the client the operator's approval is in progress so it keeps the handshake
                // alive for the full approval window instead of applying its short connect timeout.
                await SendOverBluetoothAsync(NewMessage(SessionControlMessage.TypeApprovalPending))
                    .ConfigureAwait(false);

                if (!approve(_peerDeviceName))
                {
                    // Tell the client it was declined, then drop the link. RFCOMM is in-order, so the
                    // client reads REJECT before the EOF and tears down intentionally (no reconnect).
                    await SendOverBluetoothAsync(NewMessage(SessionControlMessage.TypeSessionReject))
                        .ConfigureAwait(false);
                    _bluetooth.Disconnect();
                    throw new OperationCanceledException("The connection was declined on the PC.");
                }

                // Approval can take a while — it waits on the operator. If the client gave up and
                // dropped the link during that wait, do NOT mint a token or send our magic: the socket
                // is dead (and the Bluetooth transport no longer silently reconnects), so completing the
                // handshake would only produce a half-open session. Abort so connect_hybrid fails fast
                // and the app re-listens for the client's fresh reconnect.
                if (!_bluetooth.IsConnected())
                    throw new OperationCanceledException("Bluetooth link dropped while awaiting approval.");

                await SendOverBluetoothAsync(magic).ConfigureAwait(false);

                // IsConnected() above cannot see a *half-open* RFCOMM socket — the phone abandoned the
                // link during the slow approval but the BT stack hasn't surfaced an EOF yet, so the
                // socket still looks alive. Require the client to echo SESSION_CONFIRM after it receives
                // our magic: a live phone replies at once; a gone/half-open one never does, so we time
                // out and abort instead of declaring a dead session "connected" (the exact "PC connected
                // but phone isn't" symptom). The app then re-listens for the phone's fresh reconnect.
                await _confirmReceived.Task
                    .WaitAsync(TimeSpan.FromMilliseconds(CoreConfig.SessionJoinAckTimeoutMs))
                    .ConfigureAwait(false);

                ConnectionContext.Instance.SetSessionToken(Guid.NewGuid().ToString());
            }
            else
            {
                // Ungated path (no approval, or client): send our magic, then wait for the peer's.
                await SendOverBluetoothAsync(magic).ConfigureAwait(false);
                await _peerMagicReceived.Task
                    .WaitAsync(TimeSpan.FromMilliseconds(CoreConfig.BtHandshakeTimeoutMs))
                    .ConfigureAwait(false);

                if (_isServer)
                    ConnectionContext.Instance.SetSessionToken(Guid.NewGuid().ToString());
            }
        }

        /// <summary>
        /// Picks the transport for a logical send of <paramref name="payloadBytes"/> bytes. Small
        /// payloads always go over Bluetooth. A large payload brings Wi-Fi up on demand and waits for
        /// it; if Wi-Fi cannot be established in time it falls back to Bluetooth (degraded, but the
        /// data still flows).
        /// </summary>
        public async Task<ITransport> TransportForSendAsync(int payloadBytes)
        {
            if (payloadBytes <= CoreConfig.HybridSmallThresholdBytes)
                return _bluetooth;
            return await AcquireWifiOrFallbackAsync().ConfigureAwait(false);
        }

        /// <summary>Synchronous counterpart of <see cref="TransportForSendAsync"/> for the blocking send path.</summary>
        public ITransport TransportForSend(int payloadBytes) =>
            TransportForSendAsync(payloadBytes).GetAwaiter().GetResult();

        /// <summary>
        /// Brings Wi-Fi up (running the WIFI_CONNECT handshake if needed) and waits for it to become
        /// usable, returning the Wi-Fi transport on success. If Wi-Fi cannot be established within the
        /// retry budget it falls back to Bluetooth so the send still succeeds — degraded but reliable.
        /// Used both for the first large send on a stream and to revive a stream's Wi-Fi link after an
        /// idle teardown.
        /// </summary>
        public async Task<ITransport> AcquireWifiOrFallbackAsync()
        {
            lock (_wifiLock)
            {
                // Wi-Fi dropped unexpectedly since it was marked up (a drop bypasses
                // DisconnectWifiForIdle, so nothing reset the state machine). Reset it here or the
                // already-completed ready gate below would hand back the DEAD link and the send
                // would park on the transport's gate until it times out.
                if (_wifiUp && !_wifi.IsConnected())
                {
                    _wifiUp = false;
                    _wifiActivating = false;
                    _wifiReady = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                }
            }

            if (_wifiUp && _wifi.IsConnected())
                return _wifi;

            for (int attempt = 0; attempt < CoreConfig.WifiReconnectMaxAttempts && !_disposed; attempt++)
            {
                TriggerWifiConnect();
                try
                {
                    await CurrentWifiReadyTask()
                        .WaitAsync(TimeSpan.FromMilliseconds(CoreConfig.BtConnectTimeoutMs))
                        .ConfigureAwait(false);
                    return _wifi;
                }
                catch (TimeoutException)
                {
                    // Timed out waiting for the Wi-Fi handshake. If the bring-up failed it already
                    // reset _wifiActivating, so TriggerWifiConnect restarts on the next iteration.
                    // If the handshake is still in flight, TriggerWifiConnect is a no-op and we
                    // just wait another window.
                }
                catch
                {
                    break; // unexpected error — skip remaining retries
                }
            }
            // All retries exhausted — fall back to Bluetooth so the send still succeeds.
            return _bluetooth;
        }

        /// <summary>Synchronous counterpart of <see cref="AcquireWifiOrFallbackAsync"/>.</summary>
        public ITransport AcquireWifiOrFallback() =>
            AcquireWifiOrFallbackAsync().GetAwaiter().GetResult();

        /// <summary>Routes a recognised session-control frame. Registered with the shared context dispatcher.</summary>
        public void OnSessionControl(SessionControlMessage message)
        {
            switch (message.Type)
            {
                case SessionControlMessage.TypeBtMagic:
                    // Remember the peer's Wi-Fi address so the app can reach it (or pre-fill the IP
                    // field) without manual entry. The peer's BT_MAGIC is the earliest we learn it.
                    if (!string.IsNullOrWhiteSpace(message.WifiHost))
                        ConnectionContext.Instance.SetPeerWifiHost(message.WifiHost);
                    _peerDeviceName = message.DeviceName;
                    _peerMagicReceived.TrySetResult();
                    break;
                case SessionControlMessage.TypeWifiConnectReq:
                    if (_isServer) TriggerWifiConnect();
                    break;
                case SessionControlMessage.TypeWifiConnectReady:
                    if (!_isServer) _ = HandleWifiConnectReadyAsync(message);
                    break;
                case SessionControlMessage.TypeSessionJoin:
                    if (_isServer) _ = HandleSessionJoinAsync(message);
                    break;
                case SessionControlMessage.TypeSessionJoinAck:
                    if (!_isServer) MarkWifiReady();
                    break;
                case SessionControlMessage.TypeSessionConfirm:
                    // The client confirmed it received our BT_MAGIC, so the link is live — release the
                    // server's post-approval wait.
                    if (_isServer) _confirmReceived.TrySetResult();
                    break;
                case SessionControlMessage.TypeWifiIdleClose:
                    // The peer is closing the idle Wi-Fi link. Tear our side down intentionally too
                    // (without echoing the announce back) so the close is never mistaken for an
                    // unexpected drop.
                    TearDownWifi(announcePeer: false);
                    break;
            }
        }

        public void Dispose()
        {
            _disposed = true;
            _idleTimer?.Dispose();
            _idleTimer = null;
        }

        // ── Wi-Fi bring-up ────────────────────────────────────────────────

        /// <summary>
        /// Kicks off the Wi-Fi bring-up exactly once per cycle. The server starts its listener and
        /// announces it; the client asks the server to do so. Re-entrant calls (a duplicate
        /// WIFI_CONNECT_REQ, or a second large payload) are ignored while one bring-up is in flight.
        /// </summary>
        private void TriggerWifiConnect()
        {
            lock (_wifiLock)
            {
                if (_disposed || _wifiUp || _wifiActivating)
                    return;
                _wifiActivating = true;
            }

            if (_isServer)
                _ = StartWifiServerAndAnnounceAsync();
            else
                _ = SendOverBluetoothAsync(NewMessage(SessionControlMessage.TypeWifiConnectReq));
        }

        private async Task StartWifiServerAndAnnounceAsync()
        {
            try
            {
                // Connect(null) binds the listener synchronously before it yields, so the SDP-style
                // race is closed: by the time we send READY the client can safely dial in.
                _ = _wifi.Connect(null);

                var ready = NewMessage(SessionControlMessage.TypeWifiConnectReady);
                ready.SessionToken = ConnectionContext.Instance.GetSessionToken();
                ready.WifiHost = NetworkUtils.GetLocalWifiIpAddress() ?? "127.0.0.1";
                ready.WifiPort = CoreConfig.DefaultPort;
                await SendOverBluetoothAsync(ready).ConfigureAwait(false);
            }
            catch
            {
                ResetWifiActivation();
            }
        }

        private async Task HandleWifiConnectReadyAsync(SessionControlMessage message)
        {
            try
            {
                ConnectionContext.Instance.SetSessionToken(message.SessionToken!);
                int connectTimeoutSeconds = Math.Max(1, CoreConfig.BtConnectTimeoutMs / 1000);
                await _wifi.Connect(message.WifiHost, connectTimeoutSeconds).ConfigureAwait(false);

                var join = NewMessage(SessionControlMessage.TypeSessionJoin);
                join.SessionToken = message.SessionToken;
                await SendOverWifiAsync(join).ConfigureAwait(false);
            }
            catch
            {
                ResetWifiActivation();
            }
        }

        private async Task HandleSessionJoinAsync(SessionControlMessage message)
        {
            string? expected = ConnectionContext.Instance.GetSessionToken();
            if (string.IsNullOrEmpty(expected) || expected != message.SessionToken)
            {
                // Token mismatch — drop the Wi-Fi socket without acknowledging. Bluetooth stays up.
                _wifi.Disconnect();
                ResetWifiActivation();
                return;
            }

            await SendOverWifiAsync(NewMessage(SessionControlMessage.TypeSessionJoinAck)).ConfigureAwait(false);
            MarkWifiReady();
        }

        private void MarkWifiReady()
        {
            lock (_wifiLock)
            {
                _wifiUp = true;
                _wifiActivating = false;
                _wifiReady.TrySetResult();
            }
            StartIdleTimer();
        }

        private void ResetWifiActivation()
        {
            lock (_wifiLock)
            {
                _wifiActivating = false;
            }
        }

        // ── Idle teardown ─────────────────────────────────────────────────

        private void StartIdleTimer()
        {
            if (_idleTimer == null)
                _idleTimer = new Timer(_ => CheckWifiIdle(), null, IdleCheckPeriodMs, IdleCheckPeriodMs);
        }

        private const int IdleCheckPeriodMs = 5_000;

        private void CheckWifiIdle()
        {
            if (_disposed || !_wifiUp)
                return;
            double idleMs = (DateTime.UtcNow - new DateTime(_wifi.LastActivityTicks, DateTimeKind.Utc)).TotalMilliseconds;
            if (idleMs >= CoreConfig.WifiIdleTimeoutMs)
                DisconnectWifiForIdle();
        }

        /// <summary>
        /// Tears down the idle Wi-Fi link intentionally, announcing it to the peer first so BOTH
        /// sides close on purpose. Because Bluetooth is still up the ref-counted
        /// <see cref="ConnectionContext.NotifyTransportDisconnected"/> does not abort any channels —
        /// they simply continue over Bluetooth until the next large payload re-runs the bring-up.
        /// </summary>
        private void DisconnectWifiForIdle() => TearDownWifi(announcePeer: true);

        /// <summary>
        /// Shared Wi-Fi teardown for both the local idle timer (<paramref name="announcePeer"/> true —
        /// tell the peer over Bluetooth BEFORE closing, so its side is intentional too, not a
        /// mistaken "unexpected drop") and the peer's WIFI_IDLE_CLOSE announce (false — never echo,
        /// or the two sides would ping-pong).
        /// </summary>
        private void TearDownWifi(bool announcePeer)
        {
            lock (_wifiLock)
            {
                if (!_wifiUp)
                    return;
                _wifiUp = false;
                _wifiActivating = false;
                // Fresh incomplete gate so the next large send waits for a new bring-up.
                _wifiReady = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            }
            if (announcePeer)
            {
                // Best-effort: if Bluetooth is down the whole session is ending anyway.
                try
                {
                    SendOverBluetoothAsync(NewMessage(SessionControlMessage.TypeWifiIdleClose))
                        .GetAwaiter().GetResult();
                }
                catch { }
            }
            try { _wifi.Disconnect(); } catch { }
        }

        // ── Frame helpers ─────────────────────────────────────────────────

        private Task CurrentWifiReadyTask()
        {
            lock (_wifiLock)
            {
                return _wifiReady.Task;
            }
        }

        private static SessionControlMessage NewMessage(string type) =>
            new SessionControlMessage { Type = type, MagicBytes = CoreConfig.MagicBytes };

        private Task SendOverBluetoothAsync(SessionControlMessage message) =>
            _bluetooth.SendRaw(BuildControlFrame(message));

        private Task SendOverWifiAsync(SessionControlMessage message) =>
            _wifi.SendRaw(BuildControlFrame(message));

        private byte[] BuildControlFrame(SessionControlMessage message)
        {
            byte[] body = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(message));
            return _protocol.BuildFrame(CoreConfig.ControlChannelId, body, CoreConfig.FlagControl);
        }
    }
}

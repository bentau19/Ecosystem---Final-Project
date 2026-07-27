using System;
using System.Collections.Concurrent;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using TauSync.Core;
using TauSync.Implementations.Protocol;
using TauSync.Implementations.Security;
using TauSync.Implementations.Transport;
using TauSync.Interfaces;
using TauSync.Models;

namespace TauSync.Implementations.Management
{
    /// <summary>
    /// Central hub (Singleton) for ID management and packet routing per TauSync v3.
    /// Branch on TargetID first; TargetID=0 = discovery (require CONTROL + MagicBytes); TargetID&gt;0 = pass to handler.
    /// FIN cleanup: remove from both _routingMap and _targetMap.
    /// IDs are never reused within a session (24-bit monotonic counter, reset on reconnect),
    /// so stale FIN frames addressed to a closed channel hit an unmapped ID and are dropped
    /// instead of corrupting a newer channel that recycled the same ID.
    /// </summary>
    public sealed class ConnectionContext
    {
        private static readonly ConnectionContext _instance = new ConnectionContext();

        public static ConnectionContext Instance => _instance;

        private const int MinId = 1;
        private const int MaxId = 0xFFFFFF;

        private int _nextCorrelationId = MinId;

        /// <summary>Guards the wrap-around increment in <see cref="ReserveId"/> so two threads cannot both reset to MinId and hand out a duplicate ID.</summary>
        private readonly object _idLock = new object();

        /// <summary>
        /// IDs eligible for reuse, keyed for idempotent add (prevents double-recycle when both
        /// FIN-dispatch and <see cref="ConnectionManager.CompleteStream"/> release the same ID).
        /// IDs are added only after a grace period so that in-flight FIN frames targeting a recycled
        /// ID don't corrupt the new handler registered for that ID.
        /// </summary>
        private readonly ConcurrentDictionary<int, byte> _releasedIds = new();

        private const int IdRecycleDelayMs = 2000;

        /// <summary>LocalID -> handler(payload, flags). Handler decides DATA vs in-band CONTROL.</summary>
        private readonly ConcurrentDictionary<int, Action<byte[], byte>> _routingMap = new();

        /// <summary>LocalID -> PeerID. For sending: use TargetID = _targetMap[localId] in TPack header.</summary>
        private readonly ConcurrentDictionary<int, int> _targetMap = new();

        /// <summary>Meeting Word -> callback(localId, peerSenderId, stream). Invoked when REQ arrives on TargetID=0.</summary>
        private readonly ConcurrentDictionary<string, Action<int, int, Stream>> _serviceRegistry = new();

        /// <summary>
        /// REQ payloads queued per word when a discovery frame arrives before <see cref="RegisterService"/> was called
        /// (e.g. client calls <c>Connect(word)</c> before the server has registered the same word). Drained when the service registers.
        /// </summary>
        private readonly ConcurrentDictionary<string, ConcurrentQueue<byte[]>> _pendingDiscoveryByWord = new();

        private const int MaxPendingDiscoveryPerWord = 64;

        private readonly ITransport _wifiTransport;
        private readonly ITransport _bluetoothTransport;

        /// <summary>
        /// Number of transports currently brought up by the app (intentional connects minus
        /// intentional disconnects). Unexpected drops do NOT change this count — they
        /// reconnect under the hood — so the session only ends when the last transport is
        /// explicitly disconnected. See <see cref="NotifyTransportDisconnected"/>.
        /// </summary>
        private int _activeTransportCount;

        /// <summary>
        /// Hybrid session token. Generated server-side after the BT_MAGIC exchange and shared with
        /// the client inside WIFI_CONNECT_READY; the client echoes it in SESSION_JOIN so the server
        /// can prove the incoming Wi-Fi socket belongs to the same session as the Bluetooth link.
        /// Null until a hybrid session is established; cleared by <see cref="Reset"/>.
        /// </summary>
        private volatile string? _sessionToken;

        /// <summary>
        /// The peer's Wi-Fi IPv4 address, learned from the WifiHost field of the peer's BT_MAGIC frame
        /// during the hybrid handshake. Lets the app connect Wi-Fi (or display/pre-fill the address)
        /// without the user typing an IP — the Bluetooth link discovers it. Null until a hybrid
        /// BT_MAGIC carrying a host arrives; cleared by <see cref="Reset"/>.
        /// </summary>
        private volatile string? _peerWifiHost;

        /// <summary>
        /// Per-session crypto: runs the ECDH key exchange and encrypts/decrypts frame payloads once a
        /// shared key is derived. Same lifecycle as <see cref="_sessionToken"/> — cleared by <see cref="Reset"/>.
        /// </summary>
        private readonly SecuritySession _securitySession = new SecuritySession();

        /// <summary>Completed when the peer's KEY_EXCHANGE public key arrives, unblocking <see cref="CompleteKeyExchangeAsync"/>.</summary>
        private volatile TaskCompletionSource<string>? _peerKeyReceived;

        /// <summary>Our ephemeral ECDH public key (base64 SPKI) for the in-flight exchange.</summary>
        private volatile string? _localPublicKey;

        /// <summary>Used to build the (plaintext) KEY_EXCHANGE frame; framing only, no routing state.</summary>
        private readonly IProtocolHandler _keyExchangeProtocol = new ProtocolHandler();

        private ConnectionContext()
        {
            _wifiTransport = new SocketTransport();
            _bluetoothTransport = new BluetoothTransport();
        }

        /// <summary>True once the ECDH exchange has derived a key and payload encryption is active.</summary>
        public bool IsEncryptionActive => _securitySession.IsEncryptionActive;

        /// <summary>Encrypts a frame payload (no-op while inactive or empty). Called from <see cref="ProtocolHandler.BuildFrame"/>.</summary>
        public byte[] EncryptPayload(byte[] payload) => _securitySession.EncryptPayload(payload);

        /// <summary>Decrypts a frame payload (no-op while inactive or empty). Called from <see cref="Dispatch"/> after routing.</summary>
        public byte[] DecryptPayload(byte[] payload) => _securitySession.DecryptPayload(payload);

        /// <summary>
        /// Generates the local ECDH key pair and arms the peer-key awaiter. Call right after
        /// <see cref="Reset"/> and BEFORE the transport connects, so a peer KEY_EXCHANGE that arrives
        /// immediately can be completed synchronously on the receive thread (closing the race where the
        /// peer's first encrypted frame is processed before encryption activates).
        /// </summary>
        public void BeginKeyExchange()
        {
            _peerKeyReceived = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
            _localPublicKey = _securitySession.GenerateLocalPublicKey();
        }

        /// <summary>
        /// Sends our KEY_EXCHANGE public key over <paramref name="transport"/> and awaits the peer's,
        /// then derives the shared key. The exchange is symmetric (both sides send and receive) and runs
        /// as the very first traffic on the primary transport, before BT_MAGIC / meeting-word discovery.
        /// Idempotent with the synchronous derivation done in <see cref="TryHandleKeyExchange"/>.
        /// </summary>
        public async Task CompleteKeyExchangeAsync(ITransport transport)
        {
            if (transport == null) throw new ArgumentNullException(nameof(transport));
            if (_peerKeyReceived == null)
                BeginKeyExchange();
            TaskCompletionSource<string> peerKeyReceived = _peerKeyReceived!;

            var message = new KeyExchangeMessage
            {
                MagicBytes = CoreConfig.MagicBytes,
                Type = KeyExchangeMessage.TypeKeyExchange,
                PublicKey = _localPublicKey
            };
            byte[] body = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(message));
            byte[] frame = _keyExchangeProtocol.BuildFrame(CoreConfig.ControlChannelId, body, CoreConfig.FlagControl);
            await transport.SendRaw(frame).ConfigureAwait(false);

            string peerKey = await peerKeyReceived.Task
                .WaitAsync(TimeSpan.FromMilliseconds(CoreConfig.KeyExchangeTimeoutMs))
                .ConfigureAwait(false);

            // Safety net: the dispatch path normally derives the key synchronously when the peer frame
            // arrives. CompleteExchange is idempotent, so this is a no-op if that already happened.
            _securitySession.CompleteExchange(peerKey);
        }

        /// <summary>Stores the hybrid session token (see <see cref="_sessionToken"/>).</summary>
        public void SetSessionToken(string token) => _sessionToken = token;

        /// <summary>Returns the hybrid session token, or null if no hybrid session is established.</summary>
        public string? GetSessionToken() => _sessionToken;

        /// <summary>Stores the peer's Wi-Fi IPv4 address learned over Bluetooth (see <see cref="_peerWifiHost"/>).</summary>
        public void SetPeerWifiHost(string? host) => _peerWifiHost = host;

        /// <summary>Returns the peer's Wi-Fi IPv4 address learned over Bluetooth, or null if not yet known.</summary>
        public string? GetPeerWifiHost() => _peerWifiHost;

        public async Task InitializeTransports(string?targetId, int? timeoutSeconds = null)
        {
            if (_wifiTransport.IsConnected())
                throw new InvalidOperationException("Transport already connected.");
            if (_wifiTransport == null)
                throw new InvalidOperationException("Not initialized.");
            // Clear any routing/discovery state left over from a previous session before
            // re-establishing. Without this, stale handlers and pending REQs from the
            // prior connection get replayed onto the new session's frames.
            Reset();
            // Wi-Fi-only mode: this is the session's ONLY link, so an unexpected drop must silently
            // reconnect (a prior hybrid session may have left auto-reconnect disabled on the singleton).
            GetWifiTransportAsSocket().AutoReconnect = true;
            // Arm the key exchange before connecting so a peer KEY_EXCHANGE arriving the instant the
            // link is up is captured (and derived synchronously) rather than lost.
            BeginKeyExchange();
            await _wifiTransport.Connect(targetId, timeoutSeconds).ConfigureAwait(false);
        }

        /// <summary>
        /// Aborts every open channel by delivering a synthetic FIN to its registered handler.
        /// Each handler responds to FIN by completing its backing <see cref="BackBufferedStream"/>,
        /// which unblocks any thread sitting in <c>Read()</c> with EOF instead of hanging forever.
        ///
        /// Must be called when the transport dies (receive loop exit / explicit disconnect):
        /// without it, streams whose peer vanished without sending FIN (e.g. phone leaves
        /// Wi-Fi mid-transfer) block their readers indefinitely.
        /// </summary>
        public void AbortAllChannels()
        {
            foreach (var kvp in _routingMap)
            {
                try
                {
                    kvp.Value(Array.Empty<byte>(), CoreConfig.FlagFin);
                }
                catch
                {
                    // A failing handler must not prevent the remaining channels from being aborted.
                }
            }
            _routingMap.Clear();
            _targetMap.Clear();
        }

        /// <summary>
        /// Records that a transport has been intentionally brought up. Paired with
        /// <see cref="NotifyTransportDisconnected"/> on the matching explicit disconnect.
        /// Reconnects after an unexpected drop do NOT call this — the transport never
        /// logically left the session.
        /// </summary>
        public void NotifyTransportConnected() => Interlocked.Increment(ref _activeTransportCount);

        /// <summary>
        /// Records that a transport has been intentionally torn down. Only when the LAST
        /// live transport disconnects (count reaches zero) are the open channels aborted and
        /// the session state reset. Disconnecting one transport while another stays up (e.g.
        /// dropping Wi-Fi but keeping Bluetooth) leaves that transport's channels untouched.
        /// </summary>
        public void NotifyTransportDisconnected()
        {
            if (Interlocked.Decrement(ref _activeTransportCount) <= 0)
            {
                AbortAllChannels();
                Reset();
            }
        }

        /// <summary>
        /// Clears all routing, target, service, and discovery state accumulated during a session,
        /// and resets the ID counter. Called before re-establishing a connection so that stale
        /// handlers and pending discovery frames from a previous session are not replayed on the
        /// new session. Mirrors the Java <c>ConnectionContext.reset()</c>.
        /// </summary>
        public void Reset()
        {
            _routingMap.Clear();
            _targetMap.Clear();
            _serviceRegistry.Clear();
            _pendingDiscoveryByWord.Clear();
            _sessionToken = null;
            _peerWifiHost = null;
            _securitySession.Clear();
            _peerKeyReceived = null;
            _localPublicKey = null;
            Interlocked.Exchange(ref _nextCorrelationId, MinId);
        }

        public ITransport GetWifiTransport() => _wifiTransport;
        public SocketTransport GetWifiTransportAsSocket() => (SocketTransport)_wifiTransport;
        public ITransport GetBluetoothTransport() => _bluetoothTransport;

        /// <summary>
        /// Returns true when the underlying transport accepted a connection (server mode).
        /// Used by <see cref="ConnectionManager"/> to deterministically break the simultaneous-connect race:
        /// the server side prefers the incoming (peer) path, the client side prefers the outgoing (own) path.
        /// </summary>
        public bool IsTransportServerMode =>
            (_wifiTransport as SocketTransport)?.IsServerMode ?? false;

        /// <summary>
        /// Reserves the next channel ID. IDs are strictly monotonic within a session —
        /// never recycled — so frames that arrive late for a closed channel (e.g. a peer
        /// FIN delayed behind bulk transfer data) can never be misrouted to a newer
        /// channel. The 24-bit space (16.7M IDs) cannot realistically be exhausted in one
        /// session, and <see cref="Reset"/> restarts the counter on every reconnect.
        /// </summary>
        public int ReserveId()
        {
            foreach (var key in _releasedIds.Keys)
            {
                if (_releasedIds.TryRemove(key, out _))
                    return key;
            }

            lock (_idLock)
            {
                int id = _nextCorrelationId;
                _nextCorrelationId++;
                if (_nextCorrelationId > MaxId)
                    _nextCorrelationId = MinId;
                return id;
            }
        }


        public IReadOnlyList<string> GetPeerWaitingWords()
        {
            var result = new List<string>();
            foreach (var kvp in _pendingDiscoveryByWord)
            {
                if (kvp.Value.Count > 0)
                    result.Add(kvp.Key);
            }
            return result;
        }




        /// <summary>
        /// Releases ID: clears routing/target maps immediately. The ID itself is
        /// intentionally NOT returned to a free pool — recycling IDs allowed a delayed
        /// peer FIN (or a double release from FIN-dispatch + CompleteStream) to destroy
        /// the routing/target entries of a newer channel that had re-reserved the same
        /// ID, surfacing as "No peer route for localId N" on writes. Safe to call
        /// multiple times for the same ID.
        /// </summary>
        public void ReleaseId(int id)
        {
            if (id < MinId || id > MaxId)
                return;
            _routingMap.TryRemove(id, out _);
            _targetMap.TryRemove(id, out _);
        }

        /// <summary>PeerID to use when sending for this local task. Returns null if not bound.</summary>
        public int? GetPeerIdFor(int localId)
        {
            return _targetMap.TryGetValue(localId, out int peerId) ? peerId : null;
        }

        /// <summary>Binds localId -> peerId for sending (e.g. after initiator receives OK).</summary>
        public void SetTargetForSend(int localId, int peerId)
        {
            if (localId < MinId || localId > MaxId) return;
            _targetMap[localId] = peerId;
        }

        public void RegisterHandler(int correlationId, Action<byte[], byte> handler)
        {
            if (handler == null) throw new ArgumentNullException(nameof(handler));
            _routingMap.AddOrUpdate(correlationId, handler, (_, __) => handler);
        }

        public void UnregisterHandler(int correlationId)
        {
            _routingMap.TryRemove(correlationId, out _);
        }

        /// <summary>Registers a listener for a Meeting Word. Callback receives (localId, peerSenderId, stream).</summary>
        public void RegisterService(string word, Action<int, int, Stream> callback)
        {
            if (string.IsNullOrWhiteSpace(word)) throw new ArgumentException("Word cannot be null or empty.", nameof(word));
            if (callback == null) throw new ArgumentNullException(nameof(callback));
            string key = word.Trim();
            _serviceRegistry[key] = callback;
            DrainPendingDiscovery(key);
        }

        public void UnregisterService(string word)
        {
            if (string.IsNullOrWhiteSpace(word)) return;
            string key = word.Trim();
            _serviceRegistry.TryRemove(key, out _);
            _pendingDiscoveryByWord.TryRemove(key, out _);
        }

        /// <summary>Dispatch: check TargetID first (§0.1). targetId=0 requires CONTROL+MagicBytes; targetId&gt;0 pass to handler. FIN: cleanup both maps + ReleaseId (§0.2).</summary>
        public bool Dispatch(int targetId, byte[] payload, byte flags)
        {
            payload ??= Array.Empty<byte>();
            if (targetId > 0)
                return DispatchToExistingChannel(targetId, payload, flags);

            return DispatchDiscoveryRequest(payload, flags);
        }

        private bool DispatchToExistingChannel(int targetId, byte[] payload, byte flags)
        {
            // Transport-switch barrier frames (BARRIER / BARRIER_ACK) are handled out-of-band by the
            // hybrid manager — they carry no channel data and must not trigger FIN cleanup.
            if ((flags & (CoreConfig.FlagBarrier | CoreConfig.FlagBarrierAck)) != 0)
            {
                _channelControlListener?.Invoke(targetId, flags);
                return true;
            }

            if (!_routingMap.TryGetValue(targetId, out var handler))
                return false;

            // Decrypt only now — after the plaintext-header routing decision picked this handler — so
            // decryption is never on the routing path and dropped/empty frames cost nothing.
            payload = _securitySession.DecryptPayload(payload);
            handler(payload, flags);
            if ((flags & CoreConfig.FlagFin) != 0)
            {
                _routingMap.TryRemove(targetId, out _);
                _targetMap.TryRemove(targetId, out _);
                ReleaseId(targetId);
            }
            return true;
        }

        private bool DispatchDiscoveryRequest(byte[] payload, byte flags)
        {
            if ((flags & CoreConfig.FlagControl) == 0)
                return false;
            // Key-exchange frames arrive in plaintext, before encryption is active, as the first traffic
            // on the link. Consume them here (gated on !active so a later decrypted control frame can
            // never be mistaken for one) BEFORE any decryption, and derive the key synchronously on this
            // receive thread so the peer's first encrypted frame is never processed before activation.
            if (!_securitySession.IsEncryptionActive && TryHandleKeyExchange(payload))
                return true;
            // Now that the key exchange has been ruled out, decrypt the control payload (no-op while
            // inactive or empty) before parsing its JSON.
            payload = _securitySession.DecryptPayload(payload);
            // Hybrid session signaling (BT_MAGIC, WIFI_CONNECT_*, SESSION_JOIN*) is checked before
            // meeting-word discovery: it shares TargetID=0 + CONTROL but is keyed by a reserved
            // Type, so it never collides with a user meeting word.
            if (TryHandleSessionControl(payload))
                return true;
            if (TryParseDiscoveryCancel(payload, out TransferRequest cancel))
                return HandleDiscoveryCancel(cancel);
            if (!TryParseDiscoveryRequest(payload, out TransferRequest request))
                return false;
            if (!TryResolveServiceCallback(request, out Action<int, int, Stream> callback))
            {
                // Peer sent REQ before we registered this word — queue and report handled so the frame is not dropped.
                string? word = request.Type?.Trim();
                if (!string.IsNullOrEmpty(word))
                {
                    EnqueuePendingDiscovery(word, payload);
                    return true;
                }
                return false;
            }

            return CompleteDiscoveryHandshake(request, callback);
        }

        private void EnqueuePendingDiscovery(string word, byte[] payload)
        {
            ConcurrentQueue<byte[]> queue = _pendingDiscoveryByWord.GetOrAdd(word, _ => new ConcurrentQueue<byte[]>());
            byte[] copy = new byte[payload.Length];
            Buffer.BlockCopy(payload, 0, copy, 0, payload.Length);
            while (queue.Count >= MaxPendingDiscoveryPerWord && queue.TryDequeue(out _)) { }
            queue.Enqueue(copy);
        }

        private void DrainPendingDiscovery(string word)
        {
            if (!_pendingDiscoveryByWord.TryGetValue(word, out ConcurrentQueue<byte[]>? queue) || queue == null)
                return;

            while (queue.TryDequeue(out byte[]? payload))
            {
                if (payload == null || payload.Length == 0)
                    continue;
                if (!TryParseDiscoveryRequest(payload, out TransferRequest request))
                    continue;
                if (!TryResolveServiceCallback(request, out Action<int, int, Stream> callback))
                    continue;
                CompleteDiscoveryHandshake(request, callback);
            }
        }

        private bool CompleteDiscoveryHandshake(TransferRequest request, Action<int, int, Stream> callback)
        {
            int localId = ReserveId();
            _targetMap[localId] = request.SenderID;

            var stream = new BackBufferedStream();
            _routingMap[localId] = CreateIncomingChannelHandler(localId, stream);

            ScheduleServiceCallback(callback, localId, request.SenderID, stream);
            return true;
        }

        private Action<byte[], byte> CreateIncomingChannelHandler(int localId, BackBufferedStream stream)
        {
            return (payload, flags) =>
            {
                if (payload != null && payload.Length > 0)
                    stream.WriteChunk(payload);
                if ((flags & CoreConfig.FlagFin) != 0)
                {
                    stream.Complete();
                    CleanupLocalId(localId);
                }
            };
        }

        private void ScheduleServiceCallback(Action<int, int, Stream> callback, int localId, int peerSenderId, BackBufferedStream stream)
        {
            _ = Task.Run(() =>
            {
                try
                {
                    callback(localId, peerSenderId, stream);
                }
                catch
                {
                    CleanupLocalId(localId);
                    stream.Dispose();
                    throw;
                }
            });
        }

        private void CleanupLocalId(int localId)
        {
            _routingMap.TryRemove(localId, out _);
            _targetMap.TryRemove(localId, out _);
            ReleaseId(localId);
        }

        /// <summary>
        /// Hybrid session-control callback. Registered by the hybrid <see cref="ConnectionManager"/>;
        /// invoked for every recognised session-control frame (BT_MAGIC, WIFI_CONNECT_*, SESSION_JOIN*)
        /// arriving on TargetID=0. The coordinator infers the source transport from the message type,
        /// so the source need not be passed here.
        /// </summary>
        private Action<SessionControlMessage>? _sessionControlListener;

        /// <summary>Registers the hybrid session-control callback (see <see cref="_sessionControlListener"/>).</summary>
        public void RegisterSessionControlListener(Action<SessionControlMessage> listener)
        {
            _sessionControlListener = listener ?? throw new ArgumentNullException(nameof(listener));
        }

        /// <summary>Clears the hybrid session-control callback (e.g. on manager dispose).</summary>
        public void UnregisterSessionControlListener() => _sessionControlListener = null;

        /// <summary>
        /// Channel-control callback for transport-switch barrier frames (BARRIER / BARRIER_ACK) arriving
        /// on a channel TargetID. Registered by the hybrid <see cref="ConnectionManager"/>; receives
        /// (channelTargetId, flags). Lets the manager answer the barrier and complete pending switches
        /// without the frame being treated as channel data.
        /// </summary>
        private Action<int, byte>? _channelControlListener;

        /// <summary>Registers the channel-control (barrier) callback (see <see cref="_channelControlListener"/>).</summary>
        public void RegisterChannelControlListener(Action<int, byte> listener)
        {
            _channelControlListener = listener ?? throw new ArgumentNullException(nameof(listener));
        }

        /// <summary>Clears the channel-control (barrier) callback (e.g. on manager dispose).</summary>
        public void UnregisterChannelControlListener() => _channelControlListener = null;

        /// <summary>
        /// Routes a recognised session-control frame to the registered listener. Returns false (so
        /// the frame falls through to meeting-word discovery) when no listener is registered or the
        /// payload is not a valid session-control message.
        /// </summary>
        private bool TryHandleSessionControl(byte[] payload)
        {
            Action<SessionControlMessage>? listener = _sessionControlListener;
            if (listener == null)
                return false;
            SessionControlMessage? message = ParseSessionControl(payload);
            if (message == null)
                return false;
            listener(message);
            return true;
        }

        /// <summary>
        /// Consumes a plaintext KEY_EXCHANGE frame: derives the shared key synchronously (on the receive
        /// thread, so encryption is active before the next frame is read) and unblocks
        /// <see cref="CompleteKeyExchangeAsync"/>. Returns false for any non-KEY_EXCHANGE payload so it
        /// falls through to the normal discovery path.
        /// </summary>
        private bool TryHandleKeyExchange(byte[] payload)
        {
            KeyExchangeMessage? message = ParseKeyExchange(payload);
            if (message == null || string.IsNullOrEmpty(message.PublicKey))
                return false;
            try
            {
                // Derive now if our key pair is ready (it is, after BeginKeyExchange ran before connect).
                _securitySession.CompleteExchange(message.PublicKey);
            }
            catch
            {
                // Key pair not ready yet or malformed peer key — the driver's await + CompleteExchange
                // safety net will derive it. Never let a bad frame break dispatch.
            }
            _peerKeyReceived?.TrySetResult(message.PublicKey);
            return true;
        }

        private static KeyExchangeMessage? ParseKeyExchange(byte[] payload)
        {
            if (payload == null || payload.Length == 0)
                return null;
            try
            {
                var message = JsonSerializer.Deserialize<KeyExchangeMessage>(Encoding.UTF8.GetString(payload));
                if (message == null || message.MagicBytes != CoreConfig.MagicBytes)
                    return null;
                return message.Type == KeyExchangeMessage.TypeKeyExchange ? message : null;
            }
            catch
            {
                return null;
            }
        }

        private static SessionControlMessage? ParseSessionControl(byte[] payload)
        {
            if (payload == null || payload.Length == 0)
                return null;
            try
            {
                var message = JsonSerializer.Deserialize<SessionControlMessage>(Encoding.UTF8.GetString(payload));
                if (message == null || message.MagicBytes != CoreConfig.MagicBytes)
                    return null;
                return IsKnownSessionType(message.Type) ? message : null;
            }
            catch
            {
                return null;
            }
        }

        private static bool IsKnownSessionType(string? type) =>
            type is SessionControlMessage.TypeBtMagic
                 or SessionControlMessage.TypeWifiConnectReq
                 or SessionControlMessage.TypeWifiConnectReady
                 or SessionControlMessage.TypeSessionJoin
                 or SessionControlMessage.TypeSessionJoinAck
                 or SessionControlMessage.TypeSessionReject
                 or SessionControlMessage.TypeSessionConfirm
                 or SessionControlMessage.TypeApprovalPending
                 or SessionControlMessage.TypeWifiIdleClose;

        private bool TryParseDiscoveryRequest(byte[] payload, out TransferRequest request)
        {
            request = default!;
            TransferRequest? parsed = ParseTransferRequest(payload);
            if (parsed == null)
                return false;
            if (parsed.MagicBytes != CoreConfig.MagicBytes)
                return false;
            if (!string.Equals(parsed.Status?.Trim(), "REQ", StringComparison.OrdinalIgnoreCase))
                return false;

            request = parsed;
            return true;
        }

        /// <summary>
        /// Parses a discovery frame as a handshake cancellation (Status == "CANCEL").
        /// Same wire shape as REQ; sent by a peer whose outgoing REQ ended up unused
        /// (connect timed out, or its connect resolved via the peer path). See spec §7.8.
        /// </summary>
        private bool TryParseDiscoveryCancel(byte[] payload, out TransferRequest request)
        {
            request = default!;
            TransferRequest? parsed = ParseTransferRequest(payload);
            if (parsed == null)
                return false;
            if (parsed.MagicBytes != CoreConfig.MagicBytes)
                return false;
            if (!string.Equals(parsed.Status?.Trim(), "CANCEL", StringComparison.OrdinalIgnoreCase))
                return false;

            request = parsed;
            return true;
        }

        /// <summary>
        /// Handles a peer handshake cancellation: the peer abandoned its REQ for
        /// <c>(Type=word, SenderID)</c> and we must forget it. Two cases:
        ///
        /// <list type="number">
        ///   <item><b>REQ still queued</b> — remove exactly the queued payload whose
        ///   SenderID matches from <see cref="_pendingDiscoveryByWord"/>, so
        ///   <see cref="GetPeerWaitingWords"/> stops reporting a word nobody waits on.</item>
        ///   <item><b>REQ already handshaken</b> — the incoming channel built from that
        ///   REQ targets the cancelled SenderID. Abort it with a synthetic FIN (the
        ///   <c>AbortAllChannels</c> pattern) so any blocked reader gets EOF instead of
        ///   hanging until its read timeout, then release the local id.</item>
        /// </list>
        ///
        /// Idempotent and best-effort: a CANCEL for an unknown word/id is a no-op.
        /// </summary>
        private bool HandleDiscoveryCancel(TransferRequest cancel)
        {
            string? word = cancel.Type?.Trim();
            if (string.IsNullOrEmpty(word))
                return false;

            // ── Case 1: REQ still queued — drop the matching entry only ──────────
            if (_pendingDiscoveryByWord.TryGetValue(word, out ConcurrentQueue<byte[]>? queue) && queue != null)
            {
                var kept = new List<byte[]>();
                while (queue.TryDequeue(out byte[]? entry))
                {
                    if (entry == null)
                        continue;
                    TransferRequest? req = ParseTransferRequest(entry);
                    bool isCancelledReq = req != null
                                          && req.SenderID == cancel.SenderID
                                          && string.Equals(req.Status?.Trim(), "REQ", StringComparison.OrdinalIgnoreCase);
                    if (!isCancelledReq)
                        kept.Add(entry);
                }
                foreach (byte[] entry in kept)
                    queue.Enqueue(entry);
                if (queue.IsEmpty)
                    _pendingDiscoveryByWord.TryRemove(word, out _);
            }

            // ── Case 2: REQ already handshaken into an active incoming channel ───
            // Only the incoming channel created from that REQ targets the cancelled
            // SenderID (a peer's outgoing-attempt id); our own outgoing routes target
            // the peer's *incoming* ids, which come from a disjoint ReserveId call —
            // so this reverse lookup can never hit a live winning channel.
            foreach (var kvp in _targetMap)
            {
                if (kvp.Value != cancel.SenderID)
                    continue;
                if (_routingMap.TryGetValue(kvp.Key, out Action<byte[], byte>? handler) && handler != null)
                {
                    try
                    {
                        handler(Array.Empty<byte>(), CoreConfig.FlagFin);
                    }
                    catch
                    {
                        // A failing handler must not prevent the id cleanup below.
                    }
                }
                CleanupLocalId(kvp.Key);
                break;
            }

            return true;
        }

        private bool TryResolveServiceCallback(TransferRequest request, out Action<int, int, Stream> callback)
        {
            callback = null!;
            string? word = request.Type?.Trim();
            if (string.IsNullOrEmpty(word))
                return false;

            if (_serviceRegistry.TryGetValue(word, out var resolved))
            {
                callback = resolved;
                return true;
            }

            callback = null!;
            return false;
        }

        public bool HasHandlerFor(int id)
        {
            return _routingMap.ContainsKey(id);
        }

        private static TransferRequest? ParseTransferRequest(byte[] payload)
        {
            if (payload == null || payload.Length == 0) return null;
            try
            {
                string json = Encoding.UTF8.GetString(payload);
                return JsonSerializer.Deserialize<TransferRequest>(json);
            }
            catch
            {
                return null;
            }
        }
    }
}

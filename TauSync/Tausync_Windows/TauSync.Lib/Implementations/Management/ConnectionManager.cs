using System;
using System.Collections.Concurrent;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Channels;
using TauSync.Core;
using TauSync.Implementations.Protocol;
using TauSync.Implementations.Transport;
using TauSync.Interfaces;
using TauSync.Models;

namespace TauSync.Implementations.Management
{
    /// <summary>
    /// Connection manager per TauSync v3: both sides call Connect(word); when two peers use the same word they are paired and get a stream.
    /// </summary>
    public class ConnectionManager : IConnectionManager
    {
        /// <summary>
        /// Primary transport: control traffic and small payloads. In Wi-Fi-only mode this is the
        /// <see cref="SocketTransport"/>; in hybrid mode it is the always-on Bluetooth transport.
        /// </summary>
        private ITransport? _primaryTransport;

        /// <summary>Secondary (lazy Wi-Fi) transport in hybrid mode; null in single-transport mode.</summary>
        private readonly ITransport? _secondaryTransport;

        /// <summary>Hybrid session orchestrator; null in single-transport mode (no routing/handshake).</summary>
        private readonly HybridSessionCoordinator? _hybrid;

        private readonly IProtocolHandler _protocolHandler;
        /// <summary>Per-word queue of incoming connections (when the other side sent REQ first).</summary>
        private readonly ConcurrentDictionary<string, Channel<Stream>> _incomingByWord = new();
        /// <summary>
        /// Words with an unresolved Connect() in flight. Guards against concurrent same-word
        /// handshakes, which would clobber the single service-registry slot and orphan one of
        /// the paired streams on the peer side (silent hang, no error). Keyed by trimmed word,
        /// case-sensitive — matching how <see cref="ConnectionContext.RegisterService"/> keys.
        /// </summary>
        private readonly ConcurrentDictionary<string, byte> _inFlightWords = new();
        /// <summary>
        /// The last transport each stream actually sent data over. Routing is decided per send by the
        /// caller's Wi-Fi flag, so a stream may use Bluetooth for one write and Wi-Fi for the next — but
        /// a single send is never split across both links (its frames all ride the one chosen link,
        /// staying ordered). This map lets <see cref="CompleteStream"/> send the FIN over the same link
        /// as the stream's final data, so the FIN cannot overtake that data on the other transport.
        /// </summary>
        private readonly ConcurrentDictionary<int, ITransport> _lastTransportByStream = new();

        /// <summary>
        /// Pending transport-switch barriers, keyed by local channel id. When a stream switches the link
        /// it sends on, the sender parks a <see cref="TaskCompletionSource"/> here and waits for the
        /// peer's BARRIER_ACK before sending on the new link, so the new (faster) link's data cannot
        /// overtake the old link's still-in-flight data at the receiver.
        /// </summary>
        private readonly ConcurrentDictionary<int, TaskCompletionSource> _pendingBarriers = new();
        private bool _disposed;

        public event EventHandler<Exception>? ErrorOccurred;

        public ConnectionManager(bool hybrid = true)
        {
            _protocolHandler = new ProtocolHandler();
            var ctx = ConnectionContext.Instance;
            if (hybrid)
            {
                var bt   = ctx.GetBluetoothTransport();
                var wifi = ctx.GetWifiTransportAsSocket();
                _primaryTransport   = bt;
                _secondaryTransport = wifi;
                // The lazy Wi-Fi secondary must not silently redial after a drop — the coordinator
                // owns Wi-Fi revival (WIFI_CONNECT_REQ handshake). A transport-level reconnect would
                // dial the peer's closed idle port (SYN→RST bursts) or adopt a socket that never
                // re-ran SESSION_JOIN.
                wifi.AutoReconnect = false;
                _hybrid = new HybridSessionCoordinator(bt, wifi, _protocolHandler);
                ctx.RegisterSessionControlListener(_hybrid.OnSessionControl);
                ctx.RegisterChannelControlListener(OnChannelControl);
            }
            else
            {
                // Single-transport manager — used directly in Wi-Fi-only mode and by new_manager() to
                // multiplex extra channels on the existing session. Bind to whichever transport is
                // actually connected: in a hybrid session that is the always-on Bluetooth primary
                // (Wi-Fi is lazy and usually down), otherwise the Wi-Fi socket. Binding to the lazy
                // Wi-Fi link here is what made new_manager() fail with "Transport not connected"
                // during a hybrid session.
                ITransport bluetooth = ctx.GetBluetoothTransport();
                Initialize(bluetooth != null && bluetooth.IsConnected()
                    ? bluetooth
                    : ctx.GetWifiTransport());
            }
        }

        /// <inheritdoc />
        public void Initialize(ITransport transport)
        {

            if (transport == null)
                throw new ArgumentNullException(nameof(transport));
            if (_primaryTransport != null)
                throw new InvalidOperationException("Already initialized.");
            _primaryTransport = transport;
        }

        /// <summary>
        /// Sets the Bluetooth connection-approval gate for a hybrid manager (no-op otherwise). The
        /// callback runs on the server (PC) right after a client connects and before the session
        /// completes; given the client's device name it returns true to accept or false to reject.
        /// Must be set before <see cref="ConnectTransport"/>.
        /// </summary>
        public void SetBtApprovalCallback(Func<string?, bool>? approve)
        {
            if (_hybrid != null)
                _hybrid.ApprovalCallback = approve;
        }

        /// <inheritdoc />
        public async Task ConnectTransport(string? targetId, int? timeoutSeconds = null)
        {
            if (_hybrid != null)
            {
                // Hybrid: connect the Bluetooth primary directly (the manager owns its transports, so
                // the singleton's internal transport is bypassed), then derive the session key, then
                // run the BT_MAGIC handshake (now encrypted). Wi-Fi is connected lazily later.
                ConnectionContext.Instance.Reset();
                ConnectionContext.Instance.BeginKeyExchange();
                try
                {
                    await _primaryTransport!.Connect(targetId, timeoutSeconds).ConfigureAwait(false);
                    await ConnectionContext.Instance.CompleteKeyExchangeAsync(_primaryTransport).ConfigureAwait(false);
                    await _hybrid.StartBtSessionAsync().ConfigureAwait(false);
                }
                catch
                {
                    // Never return "failed" while holding a live socket: a leaked RFCOMM link would
                    // keep handshaking with the peer after the caller has moved on (the "zombie
                    // session"). Disconnect stops advertising and drops any half-open peer.
                    try { _primaryTransport?.Disconnect(); } catch { }
                    throw;
                }
                return;
            }
            // Wi-Fi-only: BeginKeyExchange before connecting so a peer KEY_EXCHANGE arriving immediately
            // is handled synchronously; InitializeTransports calls Reset() then connects.
            await ConnectionContext.Instance.InitializeTransports(targetId, timeoutSeconds).ConfigureAwait(false);
            await ConnectionContext.Instance.CompleteKeyExchangeAsync(ConnectionContext.Instance.GetWifiTransport()).ConfigureAwait(false);
        }

        /// <inheritdoc />
        public bool IsConnected() => _primaryTransport?.IsConnected() ?? false;


        public void Disconnect()  {
            if (_disposed) {
                    return;
            }
            // Disconnect every live transport. With ref-counting in ConnectionContext, channels are
            // aborted and state reset only once the LAST transport drops — so a hybrid session ends
            // cleanly when both Bluetooth and Wi-Fi are torn down.
            if (_secondaryTransport?.IsConnected() == true)
                _secondaryTransport.Disconnect();
            if (_primaryTransport?.IsConnected() == true)
                _primaryTransport.Disconnect();
        }

        /// <inheritdoc />
        public async Task<Stream> Connect(string word, int? timeoutSeconds = null)
        {
            ValidateConnectState(word);
            string wordTrimmed = word.Trim();
            // Reject a second Connect() while one is still in flight for the same word.
            // Two concurrent same-word handshakes clobber the single service-registry slot
            // and leave the peer with an orphaned stream that hangs forever — fail loud instead.
            if (!_inFlightWords.TryAdd(wordTrimmed, 0))
                throw new InvalidOperationException(
                    $"Connect already in progress for word '{wordTrimmed}'. " +
                    "Wait for it to resolve or use a distinct word.");
            try
            {
                // Retry on timeout up to CoreConfig.ConnectRetryCount times. ConnectCore's finally
                // cleans up all per-word state on each attempt, so each retry starts fresh.
                // The in-flight guard stays held across retries so no concurrent same-word call slips in.
                for (int attempt = 0; ; attempt++)
                {
                    try
                    {
                        return await ConnectCore(wordTrimmed, timeoutSeconds).ConfigureAwait(false);
                    }
                    catch (TimeoutException) when (attempt < CoreConfig.ConnectRetryCount && !_disposed)
                    {
                        // ConnectCore's finally already unregistered the service and removed the
                        // word channel — retry from scratch.
                    }
                }
            }
            finally
            {
                // Release the in-flight guard last, so the word only becomes reusable after
                // all per-word state (service registry, word channel) is torn down.
                _inFlightWords.TryRemove(wordTrimmed, out _);
            }
        }

        /// <summary>Runs the actual handshake for an already guard-acquired word.</summary>
        private async Task<Stream> ConnectCore(string wordTrimmed, int? timeoutSeconds)
        {
            Channel<Stream> channel = GetOrCreateWordChannel(wordTrimmed);
            RegisterWordListener(wordTrimmed, channel);

            var ctx = ConnectionContext.Instance;
            ConnectAttempt attempt = CreateConnectAttempt(ctx);
            await SendWordRequestAsync(wordTrimmed, attempt.LocalId).ConfigureAwait(false);
            try
            {
                return await ResolveConnectRaceAsync(ctx, channel, attempt, timeoutSeconds, wordTrimmed).ConfigureAwait(false);
            }
            finally
            {
                // Unregister the service listener after the connection resolves (success or failure).
                //
                // Without this cleanup, the callback registered by RegisterWordListener stays in
                // ConnectionContext._serviceRegistry after the first use. On a second transfer using
                // the same word, the incoming REQ is handled directly (bypassing _pendingDiscoveryByWord),
                // so GetPeerWaitingWords() never surfaces the word again and the app's polling loop
                // cannot trigger a second Connect() call — causing the peer to hang forever.
                ConnectionContext.Instance.UnregisterService(wordTrimmed);
                _incomingByWord.TryRemove(wordTrimmed, out _);
                // Complete the writer so the losing ReadPeerStreamAsync terminates. Without this,
                // disposing the timeout CTS (which kills its timer before it ever fires) leaves the
                // orphaned ReadAsync waiting on a token that can no longer cancel — leaking one
                // Task + Channel per successful Connect() for the process lifetime.
                channel.Writer.TryComplete();
            }
        }

        private void ValidateConnectState(string word)
        {
            if (string.IsNullOrWhiteSpace(word))
                throw new ArgumentException("Word cannot be null or empty.", nameof(word));
            if (_primaryTransport == null || !_primaryTransport.IsConnected())
                throw new InvalidOperationException("Transport not connected. ConnectTransport first.");
            if (_disposed)
                throw new ObjectDisposedException(nameof(ConnectionManager));
        }

        private Channel<Stream> GetOrCreateWordChannel(string word)
        {
            return _incomingByWord.GetOrAdd(word, _ =>
                Channel.CreateUnbounded<Stream>(new UnboundedChannelOptions { SingleReader = false, SingleWriter = false }));
        }

        private ConnectAttempt CreateConnectAttempt(ConnectionContext ctx)
        {
            int localId = ctx.ReserveId();
            var backStream = new BackBufferedStream();
            var responseTcs = new TaskCompletionSource<byte[]>();

            void Handler(byte[] payload, byte flags)
            {
                if ((flags & CoreConfig.FlagControl) != 0)
                {
                    responseTcs.TrySetResult(payload ?? Array.Empty<byte>());
                    return;
                }

                if (payload != null && payload.Length > 0)
                    backStream.WriteChunk(payload);
                if ((flags & CoreConfig.FlagFin) != 0)
                    backStream.Complete();
            }

            ctx.RegisterHandler(localId, Handler);
            return new ConnectAttempt(localId, backStream, responseTcs);
        }

        /// <summary>
        /// Resolves the simultaneous-connect race deterministically using the transport role:
        /// the TCP client always uses the outgoing (own REQ→OK) path,
        /// the TCP server always uses the incoming (peer REQ→service callback) path.
        /// This guarantees both sides pick complementary streams so data flows correctly.
        /// Falls back to the other path if the preferred one fails.
        /// </summary>
        private async Task<Stream> ResolveConnectRaceAsync(ConnectionContext ctx, Channel<Stream> channel, ConnectAttempt attempt, int? timeoutSeconds, string word)
        {
            using var timeoutCts = new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds ?? CoreConfig.HandshakeTimeoutSeconds));
            timeoutCts.Token.Register(() => attempt.ResponseTcs.TrySetException(new TimeoutException("Handshake timeout.")));

            Task<Stream> streamFromOwnRequest = WaitForOkAndBuildStreamAsync(attempt.ResponseTcs.Task, ctx, attempt.LocalId, attempt.BackStream);
            // The peer path must honour the handshake timeout too: without the token it would
            // wait on the channel forever if the peer never sends a matching REQ. This is the
            // primary path for the TCP-server side (preferOwnPath == false), so an untimed read
            // here means Connect() could hang indefinitely despite the caller's timeout.
            Task<Stream> streamFromPeerRequest = ReadPeerStreamAsync(channel, timeoutCts.Token);

            // The meeting-word handshake runs over the primary transport (Wi-Fi in single mode,
            // Bluetooth in hybrid), so the race tiebreaker reads the primary's role, not the
            // singleton context's internal transport.
            bool preferOwnPath = !(_primaryTransport?.IsServerMode ?? ctx.IsTransportServerMode);

            if (preferOwnPath)
            {
                try
                {
                    return await streamFromOwnRequest.ConfigureAwait(false);
                }
                catch
                {
                    CleanupLosingOutgoingAttempt(ctx, attempt, word);
                    return await streamFromPeerRequest.ConfigureAwait(false);
                }
            }

            try
            {
                Stream result = await streamFromPeerRequest.ConfigureAwait(false);
                CleanupLosingOutgoingAttempt(ctx, attempt, word);
                return result;
            }
            catch
            {
                try
                {
                    return await streamFromOwnRequest.ConfigureAwait(false);
                }
                catch
                {
                    // Both paths failed (typically a double timeout). Without this cleanup the
                    // outgoing attempt's handler stayed in _routingMap and its BackBufferedStream
                    // was never disposed — leaking once per failed handshake.
                    CleanupLosingOutgoingAttempt(ctx, attempt, word);
                    throw;
                }
            }
        }

        /// <summary>
        /// Awaits the peer-initiated stream from the word channel, honouring the handshake
        /// timeout. A cancelled read (timeout) is surfaced as <see cref="TimeoutException"/>
        /// so both race paths fail with the same exception type.
        /// </summary>
        private static async Task<Stream> ReadPeerStreamAsync(Channel<Stream> channel, CancellationToken ct)
        {
            try
            {
                return await channel.Reader.ReadAsync(ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                throw new TimeoutException("Handshake timeout.");
            }
            catch (ChannelClosedException)
            {
                // The word channel was completed (race already resolved elsewhere or manager
                // disposed) — surface the same exception type as the timeout path.
                throw new TimeoutException("Handshake timeout.");
            }
        }

        /// <summary>
        /// Tears down an outgoing connect attempt whose REQ ended up unused — either the
        /// connect failed (timeout / double timeout) or it resolved via the peer path.
        /// Besides the local cleanup, sends a best-effort CANCEL frame (spec §7.8) so the
        /// peer removes the now-orphaned REQ from its pending-discovery queue — or, if the
        /// peer already handshook it into an incoming channel, aborts that channel. Without
        /// the CANCEL, one-shot meeting words leak a "peer waiting" entry on the peer for
        /// the rest of the session (re-reported by GetPeerWaitingWords on every poll).
        /// </summary>
        private void CleanupLosingOutgoingAttempt(ConnectionContext ctx, ConnectAttempt attempt, string word)
        {
            // One-shot: cleanup can run more than once for the same attempt (e.g. fallback
            // path failure after the preferred path already cleaned up) — cancel only once.
            if (attempt.TryMarkAbandoned())
                TrySendWordCancel(word, attempt.LocalId);
            ctx.ReleaseId(attempt.LocalId);
            ctx.UnregisterHandler(attempt.LocalId);
            attempt.BackStream.Dispose();
        }

        /// <summary>
        /// Sends a best-effort CANCEL discovery frame for an abandoned REQ. Fire-and-forget:
        /// failures are swallowed because cancellation is an optimisation (the transport may
        /// already be dead, and an old peer simply drops unknown discovery statuses).
        /// </summary>
        private void TrySendWordCancel(string word, int localId)
        {
            try
            {
                var cancel = new TransferRequest
                {
                    MagicBytes = CoreConfig.MagicBytes,
                    SenderID = localId,
                    Type = word,
                    Status = "CANCEL"
                };

                byte[] body = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(cancel));
                byte[] frame = _protocolHandler.BuildFrame(CoreConfig.ControlChannelId, body, CoreConfig.FlagControl);
                _ = _primaryTransport?.SendRaw(frame);
            }
            catch
            {
                // Best-effort — never let a failed CANCEL break the connect cleanup path.
            }
        }

        /// <summary>
        /// Registers a per-word callback ("listener") that accepts incoming REQ handshakes,
        /// responds with OK, and publishes the created duplex stream to the word channel.
        /// </summary>
        private void RegisterWordListener(string word, Channel<Stream> channel)
        {
            ConnectionContext.Instance.RegisterService(word, (localId, peerSenderId, stream) =>
            {
                HandleWordRequest(word, channel, localId, peerSenderId, stream);
            });
        }

        private void HandleWordRequest(string word, Channel<Stream> channel, int localId, int peerSenderId, Stream stream)
        {
            try
            {
                byte[] frame = BuildOkFrame(word, localId, peerSenderId);
                _primaryTransport!.SendRaw(frame).GetAwaiter().GetResult();

                var duplex = new DuplexStream(stream, localId, this);
                channel.Writer.TryWrite(duplex);
            }
            catch (Exception ex)
            {
                ErrorOccurred?.Invoke(this, ex);
            }
        }

        private byte[] BuildOkFrame(string word, int localId, int peerSenderId)
        {
            var ok = new TransferRequest
            {
                MagicBytes = CoreConfig.MagicBytes,
                SenderID = localId,
                Type = word,
                Status = "OK"
            };

            string json = JsonSerializer.Serialize(ok);
            byte[] body = Encoding.UTF8.GetBytes(json);
            return _protocolHandler.BuildFrame(peerSenderId, body, CoreConfig.FlagControl);
        }

        /// <summary>
        /// Sends a REQ control handshake frame for the given word and local id.
        /// </summary>
        private async Task SendWordRequestAsync(string word, int localId)
        {
            var request = new TransferRequest
            {
                MagicBytes = CoreConfig.MagicBytes,
                SenderID = localId,
                Type = word,
                Status = "REQ"
            };

            byte[] reqBody = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(request));
            byte[] reqFrame = _protocolHandler.BuildFrame(CoreConfig.ControlChannelId, reqBody, CoreConfig.FlagControl);
            await _primaryTransport!.SendRaw(reqFrame).ConfigureAwait(false);
        }

        private async Task<Stream> WaitForOkAndBuildStreamAsync(Task<byte[]> responseTask, ConnectionContext ctx, int localId, BackBufferedStream backStream)
        {
            byte[] payload = await responseTask.ConfigureAwait(false);
            TransferRequest? response = ParseTransferResponse(payload);
            if (response == null || !string.Equals(response.Status?.Trim(), "OK", StringComparison.OrdinalIgnoreCase))
            {
                ctx.ReleaseId(localId);
                ctx.UnregisterHandler(localId);
                backStream.Dispose();
                throw new InvalidOperationException("Connect rejected by peer.");
            }
            ctx.SetTargetForSend(localId, response.SenderID);
            return new DuplexStream(backStream, localId, this);
        }

        /// <summary>
        /// Returns the transport for a single send, routing by the explicit <paramref name="preferWifi"/>
        /// flag. A Wi-Fi send brings the link up on demand (running the WIFI_CONNECT handshake, or
        /// reviving a link torn down for idle) and falls back to Bluetooth only if Wi-Fi cannot be
        /// established; a Bluetooth send always uses the primary link. The chosen link is recorded as
        /// the stream's last-used transport so its FIN follows the same socket (see
        /// <see cref="CompleteStream"/>). Routing is per send by design — a stream may use Bluetooth for
        /// one write and Wi-Fi for the next — but a single send is never split across both links.
        /// </summary>
        private ITransport ResolveSendTransport(int localId, bool preferWifi) =>
            ResolveSendTransport(localId, preferWifi, async: false).GetAwaiter().GetResult();

        private async Task<ITransport> ResolveSendTransportAsync(int localId, bool preferWifi) =>
            await ResolveSendTransport(localId, preferWifi, async: true).ConfigureAwait(false);

        private async Task<ITransport> ResolveSendTransport(int localId, bool preferWifi, bool async)
        {
            if (_hybrid == null)
                return _primaryTransport!;  // single transport (Wi-Fi-only or Bluetooth-only)

            ITransport chosen = preferWifi
                ? (async ? await _hybrid.AcquireWifiOrFallbackAsync().ConfigureAwait(false)
                         : _hybrid.AcquireWifiOrFallback())
                : _primaryTransport!;

            // If this stream is switching the link it sends on, drain the old link first so its
            // in-flight data cannot be overtaken by the new (faster) link at the receiver.
            if (_lastTransportByStream.TryGetValue(localId, out ITransport? last)
                && !ReferenceEquals(last, chosen) && last.IsConnected())
            {
                await BarrierBeforeSwitchAsync(localId, last).ConfigureAwait(false);
            }

            // Record the link this stream last used so its FIN follows the same socket.
            _lastTransportByStream[localId] = chosen;
            return chosen;
        }

        /// <summary>
        /// Drains the channel's <paramref name="oldTransport"/> before the stream starts sending on a
        /// different link: emits a BARRIER on the old link (so it is ordered after that link's data) and
        /// waits for the peer's BARRIER_ACK. Best-effort — a missing ACK times out
        /// (<see cref="CoreConfig.BarrierAckTimeoutMs"/>) and the send proceeds rather than hanging.
        /// </summary>
        private async Task BarrierBeforeSwitchAsync(int localId, ITransport oldTransport)
        {
            int? peerId = ConnectionContext.Instance.GetPeerIdFor(localId);
            if (peerId == null)
                return;

            var ack = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            _pendingBarriers[localId] = ack;
            try
            {
                byte[] frame = _protocolHandler.BuildFrame(peerId.Value, Array.Empty<byte>(), CoreConfig.FlagBarrier);
                await oldTransport.SendRaw(frame).ConfigureAwait(false);
                await ack.Task.WaitAsync(TimeSpan.FromMilliseconds(CoreConfig.BarrierAckTimeoutMs)).ConfigureAwait(false);
            }
            catch
            {
                // Timeout or send failure — proceed anyway (degrade to unordered, never hang).
            }
            finally
            {
                _pendingBarriers.TryRemove(localId, out _);
            }
        }

        /// <summary>
        /// Handles an inbound transport-switch barrier frame (dispatched out-of-band by
        /// <see cref="ConnectionContext"/>). A BARRIER asks us to confirm we have drained this channel's
        /// data on the link it arrived over: we reply BARRIER_ACK over the always-on Bluetooth primary
        /// (the ACK only needs to arrive — its ordering versus data is irrelevant). A BARRIER_ACK
        /// completes the sender's pending switch.
        /// </summary>
        private void OnChannelControl(int targetId, byte flags)
        {
            if ((flags & CoreConfig.FlagBarrierAck) != 0)
            {
                if (_pendingBarriers.TryGetValue(targetId, out TaskCompletionSource? ack))
                    ack.TrySetResult();
                return;
            }
            if ((flags & CoreConfig.FlagBarrier) != 0)
            {
                int? peerId = ConnectionContext.Instance.GetPeerIdFor(targetId);
                if (peerId == null)
                    return;
                byte[] frame = _protocolHandler.BuildFrame(peerId.Value, Array.Empty<byte>(), CoreConfig.FlagBarrierAck);
                _ = _primaryTransport?.SendRaw(frame);  // fire-and-forget; never block the receive loop
            }
        }

        /// <inheritdoc />
        public void SendStreamData(int localId, byte[] buffer, int offset, int count) =>
            // No explicit hint (e.g. a raw DuplexStream write with no semantics): fall back to size —
            // a payload at or above a full wire chunk is treated as large and routed over Wi-Fi.
            SendStreamData(localId, buffer, offset, count, count > CoreConfig.HybridSmallThresholdBytes);

        /// <inheritdoc />
        public void SendStreamData(int localId, byte[] buffer, int offset, int count, bool preferWifi)
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(ConnectionManager));
            if (_primaryTransport == null)
                throw new InvalidOperationException("Transport not initialized.");
            if (buffer == null)
                throw new ArgumentNullException(nameof(buffer));
            if (offset < 0 || count < 0 || offset + count > buffer.Length)
                throw new ArgumentOutOfRangeException(nameof(buffer));
            if (count <= 0)
                return;

            int? peerId = ConnectionContext.Instance.GetPeerIdFor(localId);
            if (peerId == null)
                throw new InvalidOperationException(
                    $"No peer route for localId {localId}. Handshake may not have completed; do not write before Connect(word) finishes.");

            // Route this send to one transport (Wi-Fi when flagged, else Bluetooth) and send every wire
            // frame over it, so the send is never split across links and its frames stay ordered.
            ITransport transport = ResolveSendTransport(localId, preferWifi);

            int sent = 0;
            while (sent < count)
            {
                int sliceLen = Math.Min(CoreConfig.StreamChunkSize, count - sent);
                byte[] chunk = new byte[sliceLen];
                Buffer.BlockCopy(buffer, offset + sent, chunk, 0, sliceLen);
                byte[] frame = _protocolHandler.BuildFrame(peerId.Value, chunk, 0);
                transport.SendRaw(frame).GetAwaiter().GetResult();
                sent += sliceLen;
            }
        }

        /// <inheritdoc />
        public Task SendStreamDataAsync(int localId, byte[] buffer, int offset, int count, CancellationToken cancellationToken) =>
            SendStreamDataAsync(localId, buffer, offset, count,
                count > CoreConfig.HybridSmallThresholdBytes, cancellationToken);

        /// <inheritdoc />
        public async Task SendStreamDataAsync(int localId, byte[] buffer, int offset, int count, bool preferWifi, CancellationToken cancellationToken)
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(ConnectionManager));
            if (_primaryTransport == null)
                throw new InvalidOperationException("Transport not initialized.");
            if (buffer == null)
                throw new ArgumentNullException(nameof(buffer));
            if (offset < 0 || count < 0 || offset + count > buffer.Length)
                throw new ArgumentOutOfRangeException(nameof(buffer));
            if (count <= 0)
                return;

            int? peerId = ConnectionContext.Instance.GetPeerIdFor(localId);
            if (peerId == null)
                throw new InvalidOperationException(
                    $"No peer route for localId {localId}. Handshake may not have completed; do not write before Connect(word) finishes.");

            // Route this send to one transport and send every chunk over it (see SendStreamData).
            ITransport transport = await ResolveSendTransportAsync(localId, preferWifi).ConfigureAwait(false);

            int sent = 0;
            while (sent < count)
            {
                cancellationToken.ThrowIfCancellationRequested();
                int sliceLen = Math.Min(CoreConfig.StreamChunkSize, count - sent);
                byte[] chunk = new byte[sliceLen];
                Buffer.BlockCopy(buffer, offset + sent, chunk, 0, sliceLen);
                byte[] frame = _protocolHandler.BuildFrame(peerId.Value, chunk, 0);
                await transport.SendRaw(frame).ConfigureAwait(false);
                sent += sliceLen;
            }
        }

        /// <inheritdoc />
        public void CompleteStream(int localId)
        {
            if (_disposed)
                return;
            if (_primaryTransport == null)
                return;

            int? peerId = ConnectionContext.Instance.GetPeerIdFor(localId);
            if (peerId != null)
            {
                // Send FIN over the same link the stream last sent data on, so it cannot overtake that
                // data on the other transport. Falls back to primary for a stream that was never written
                // (empty close) or whose last link is gone (idle-disconnected and already drained).
                ITransport finTransport = _lastTransportByStream.TryGetValue(localId, out ITransport? last) && last.IsConnected()
                    ? last
                    : _primaryTransport;
                byte[] finFrame = _protocolHandler.BuildFrame(peerId.Value, Array.Empty<byte>(), CoreConfig.FlagFin);
                try
                {
                    finTransport.SendRaw(finFrame).GetAwaiter().GetResult();
                }
                catch
                {
                    // Best-effort: close must never throw. If the FIN cannot be delivered (link
                    // dropping mid-close), the peer tears the channel down on its own.
                }
            }
            _lastTransportByStream.TryRemove(localId, out _);
            ConnectionContext.Instance.ReleaseId(localId);
        }

        private static TransferRequest? ParseTransferResponse(byte[] payload)
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

        private sealed class ConnectAttempt
        {
            private int _abandoned;

            public int LocalId { get; }
            public BackBufferedStream BackStream { get; }
            public TaskCompletionSource<byte[]> ResponseTcs { get; }

            public ConnectAttempt(int localId, BackBufferedStream backStream, TaskCompletionSource<byte[]> responseTcs)
            {
                LocalId = localId;
                BackStream = backStream;
                ResponseTcs = responseTcs;
            }

            /// <summary>
            /// Marks this attempt's outgoing REQ as abandoned. Returns true only on the
            /// first call so the CANCEL frame is sent exactly once per attempt.
            /// </summary>
            public bool TryMarkAbandoned() => Interlocked.Exchange(ref _abandoned, 1) == 0;
        }

        public IReadOnlyList<string> GetPeerWaitingWords()
        {
            return ConnectionContext.Instance.GetPeerWaitingWords();
        }


        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            foreach (Channel<Stream> ch in _incomingByWord.Values)
                ch.Writer.Complete();
            _incomingByWord.Clear();
            if (_hybrid != null)
            {
                ConnectionContext.Instance.UnregisterSessionControlListener();
                ConnectionContext.Instance.UnregisterChannelControlListener();
                _hybrid.Dispose();
            }
            _secondaryTransport?.Dispose();
            _primaryTransport?.Dispose();
        }
    }

    /// <summary>
    /// Duplex stream: read from a backing stream (e.g. BackBufferedStream), write sends TPack with TargetID = peer for the given localId.
    /// On dispose, sends FIN and releases the local ID.
    /// </summary>
    public sealed class DuplexStream : Stream
    {
        private readonly Stream _readStream;
        private readonly int _localId;
        private readonly IConnectionManager _connectionManager;
        private int _disposeState;  // 0 = live, 1 = disposed; flipped atomically so only one thread sends FIN
        private bool _disposed => Volatile.Read(ref _disposeState) != 0;
        private bool _finSent;

        public DuplexStream(Stream readStream, int localId, IConnectionManager connectionManager)
        {
            _readStream = readStream ?? throw new ArgumentNullException(nameof(readStream));
            _localId = localId;
            _connectionManager = connectionManager ?? throw new ArgumentNullException(nameof(connectionManager));
        }

        public override bool CanRead => true;
        public override bool CanWrite => true;
        public override bool CanSeek => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }

        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();

        public override int Read(byte[] buffer, int offset, int count)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(DuplexStream));
            return _readStream.Read(buffer, offset, count);
        }


        public override async Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(DuplexStream));
            return await _readStream.ReadAsync(buffer, offset, count, cancellationToken).ConfigureAwait(false);
        }

        public override void Write(byte[] buffer, int offset, int count)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(DuplexStream));
            if (_finSent || count <= 0) return;
            // A raw stream write carries no file/string semantics — route by size: a payload at or
            // above a full wire chunk is large → Wi-Fi, smaller → Bluetooth. The manager chunks for
            // the wire after choosing the link.
            _connectionManager.SendStreamData(_localId, buffer, offset, count,
                count > CoreConfig.HybridSmallThresholdBytes);
        }

        /// <summary>
        /// Sends over an explicitly chosen transport in hybrid mode: <paramref name="preferWifi"/>
        /// true → Wi-Fi, false → Bluetooth. The Python SDK calls this so each high-level method routes
        /// by its own semantics (write_file → Wi-Fi, write_string → Bluetooth) instead of by payload
        /// size; the plain <see cref="Write(byte[],int,int)"/> stays size-based for raw byte writes.
        /// </summary>
        public void Write(byte[] buffer, int offset, int count, bool preferWifi)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(DuplexStream));
            if (_finSent || count <= 0) return;
            _connectionManager.SendStreamData(_localId, buffer, offset, count, preferWifi);
        }

        public override async Task WriteAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(DuplexStream));
            if (_finSent || count <= 0) return;
            // Same rationale as Write — route by size, chunk inside SendStreamDataAsync.
            await _connectionManager.SendStreamDataAsync(_localId, buffer, offset, count,
                    count > CoreConfig.HybridSmallThresholdBytes, cancellationToken)
                .ConfigureAwait(false);
        }

        public override void Flush() => _readStream?.Flush();

        protected override void Dispose(bool disposing)
        {
            if (Interlocked.Exchange(ref _disposeState, 1) != 0)
                return;  // Already disposed by another thread — don't send a second FIN.

            if (disposing)
            {
                _finSent = true;
                _connectionManager.CompleteStream(_localId);
                _readStream?.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}

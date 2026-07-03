package com.example.tausync_lib.implementations.management;

import com.example.tausync_lib.core.CoreConfig;
import com.example.tausync_lib.implementations.protocol.ProtocolHandler;
import com.example.tausync_lib.implementations.transport.SocketTransport;
import com.example.tausync_lib.interfaces.IConnectionManager;
import com.example.tausync_lib.interfaces.IProtocolHandler;
import com.example.tausync_lib.interfaces.ITransport;
import com.example.tausync_lib.models.TransferRequest;
import com.google.gson.Gson;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Connection manager per TauSync v3: both sides call {@link #connect(String)} with the
 * same Meeting Word; when two peers use the same word they are paired and each gets a
 * bidirectional {@link TauSyncStream}.
 *
 * <p>Matches C# ConnectionManager.
 */
public class ConnectionManager implements IConnectionManager {

    /**
     * Primary transport: control traffic and small payloads. In Wi-Fi-only mode this is the
     * {@link SocketTransport}; in hybrid mode it is the always-on Bluetooth transport.
     */
    private ITransport primaryTransport;

    /**
     * Secondary (lazy Wi-Fi) transport in hybrid mode; null in single-transport mode.
     */
    private final ITransport secondaryTransport;

    /**
     * Hybrid session orchestrator; null in single-transport mode (no routing/handshake).
     */
    private final HybridSessionCoordinator hybrid;

    private final IProtocolHandler protocolHandler;
    private final Gson gson = new Gson();

    /**
     * Per-word queue of incoming connections (peer sent REQ before us or simultaneously).
     */
    private final ConcurrentHashMap<String, LinkedBlockingQueue<TauSyncStream>> incomingByWord =
            new ConcurrentHashMap<>();

    /**
     * Words with an unresolved connect() in flight. Guards against concurrent same-word
     * handshakes, which would clobber the single service-registry slot and orphan one of
     * the paired streams on the peer side (silent hang, no error). Keyed by trimmed word,
     * case-sensitive — matching how {@code ConnectionContext.registerService} keys.
     * Mirrors C# {@code _inFlightWords}.
     */
    private final Set<String> inFlightWords = ConcurrentHashMap.newKeySet();

    /**
     * The last transport each stream actually sent data over. Routing is decided per send by the
     * caller's Wi-Fi flag, so a stream may use Bluetooth for one write and Wi-Fi for the next — but a
     * single send is never split across both links (its frames all ride the one chosen link, staying
     * ordered). This map lets {@link #completeStream} send the FIN over the same link as the stream's
     * final data, so the FIN cannot overtake that data on the other transport. Mirrors C#
     * {@code _lastTransportByStream}.
     */
    private final ConcurrentHashMap<Integer, ITransport> lastTransportByStream = new ConcurrentHashMap<>();

    /**
     * Pending transport-switch barriers, keyed by local channel id. When a stream switches the link it
     * sends on, the sender parks a future here and waits for the peer's BARRIER_ACK before sending on
     * the new link, so the new (faster) link's data cannot overtake the old link's still-in-flight data
     * at the receiver. Mirrors C# {@code _pendingBarriers}.
     */
    private final ConcurrentHashMap<Integer, CompletableFuture<Void>> pendingBarriers = new ConcurrentHashMap<>();

    /**
     * Dedicated pool for blocking handshake operations. Avoids starving the
     * default ForkJoinPool.commonPool() on Android devices with few cores.
     */
    private static final ExecutorService HANDSHAKE_POOL =
            Executors.newCachedThreadPool(r -> {
                Thread t = new Thread(r, "TauSync-Handshake");
                t.setDaemon(true);
                return t;
            });

    private volatile boolean disposed;
    private volatile ErrorListener errorListener;

    public ConnectionManager() {
        protocolHandler = new ProtocolHandler();
        secondaryTransport = null;
        hybrid = null;
        // Single-transport manager — used directly in Wi-Fi-only mode and by newManager() to
        // multiplex extra channels on the existing session. Bind to whichever transport is actually
        // connected: in a hybrid session that is the always-on Bluetooth primary (Wi-Fi is lazy and
        // usually down), otherwise the Wi-Fi socket. Binding to the lazy Wi-Fi link here is what made
        // newManager().connect(word) fail with "Transport not connected" during a hybrid session.
        ConnectionContext ctx = ConnectionContext.getInstance();
        ITransport bluetooth = ctx.getBluetoothTransport();
        ITransport transport = (bluetooth != null && bluetooth.isConnected())
                ? bluetooth
                : ctx.getWifiTransport();
        if (transport == null) {
            throw new IllegalStateException("ConnectionContext has no transport.");
        }
        initialize(transport);
    }

    /**
     * Hybrid constructor: {@code primary} is the always-on Bluetooth link (control + small payloads)
     * and {@code secondary} is the lazy Wi-Fi link (large payloads). The manager routes each logical
     * send by size and runs the BT_MAGIC / SESSION_JOIN handshakes itself; the caller just uses it
     * like any other manager.
     */
    public ConnectionManager(ITransport primary, ITransport secondary) {
        protocolHandler = new ProtocolHandler();
        if (primary == null)
            throw new IllegalArgumentException("primary transport must not be null");
        if (secondary == null)
            throw new IllegalArgumentException("secondary transport must not be null");
        if (!(secondary instanceof SocketTransport)) {
            throw new IllegalArgumentException("The secondary (Wi-Fi) transport must be a SocketTransport.");
        }
        primaryTransport = primary;
        secondaryTransport = secondary;
        hybrid = new HybridSessionCoordinator(primary, (SocketTransport) secondary, protocolHandler);
        ConnectionContext.getInstance().registerSessionControlListener(hybrid::onSessionControl);
        ConnectionContext.getInstance().registerChannelControlListener(this::onChannelControl);
    }

    @Override
    public void initialize(ITransport transport) {
        if (transport == null) throw new IllegalArgumentException("transport must not be null");
        if (primaryTransport != null) throw new IllegalStateException("Already initialized.");
        primaryTransport = transport;
    }

    @Override
    public CompletableFuture<Void> connectTransport(String targetId) {
        return connectTransport(targetId, null);
    }

    @Override
    public CompletableFuture<Void> connectTransport(String targetId, Integer timeoutSeconds) {
        return CompletableFuture.runAsync(() -> {
            try {
                if (hybrid != null) {
                    // Hybrid: connect the Bluetooth primary directly (the manager owns its
                    // transports, so the singleton's internal transport is bypassed), then run the
                    // BT_MAGIC handshake. Wi-Fi is connected lazily on the first large payload.
                    ConnectionContext ctx = ConnectionContext.getInstance();
                    ctx.reset();
                    // Register the BT primary so a secondary manager from newManager() binds to this
                    // always-on link rather than the lazy Wi-Fi socket. Done after reset() (which
                    // clears it) and before connect so it is in place for the whole session.
                    ctx.setBluetoothTransport(primaryTransport);
                    // Arm the key exchange before connecting, then derive the session key right after
                    // the link is up and before the BT_MAGIC handshake (which is now encrypted).
                    ctx.beginKeyExchange();
                    try {
                        primaryTransport.connect(targetId, timeoutSeconds).get();
                        ctx.completeKeyExchange(primaryTransport);
                        hybrid.startBtSession();
                    } catch (Exception e) {
                        // Never return "failed" while holding a live socket: a leaked RFCOMM link
                        // would keep handshaking with the peer after the caller has moved on (the
                        // "zombie session" — the PC completes a connection no app owns).
                        try { primaryTransport.disconnect(); } catch (Exception ignored) {}
                        throw e;
                    }
                } else {
                    // Wi-Fi-only: initializeTransports calls reset() + beginKeyExchange() + connect;
                    // derive the key right after.
                    ConnectionContext ctx = ConnectionContext.getInstance();
                    ctx.initializeTransports(targetId, timeoutSeconds);
                    ctx.completeKeyExchange(ctx.getWifiTransport());
                }
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }, HANDSHAKE_POOL);
    }

    @Override
    public boolean isConnected() {
        return primaryTransport != null && primaryTransport.isConnected();
    }

    @Override
    public CompletableFuture<TauSyncStream> connect(String word) {
        return connect(word, CoreConfig.HANDSHAKE_TIMEOUT_SECONDS);
    }

    @Override
    public CompletableFuture<TauSyncStream> connect(String word, int timeoutSec) {
        validateConnectState(word);
        String wordTrimmed = word.trim();

        // Reject a second connect() while one is still in flight for the same word.
        if (!inFlightWords.add(wordTrimmed)) {
            throw new IllegalStateException(
                    "Connect already in progress for word '" + wordTrimmed
                            + "'. Wait for it to resolve or use a distinct word.");
        }
        try {
            return connectWithRetry(wordTrimmed, timeoutSec, CoreConfig.CONNECT_RETRY_COUNT);
        } catch (RuntimeException | Error e) {
            inFlightWords.remove(wordTrimmed);
            throw e;
        }
    }

    /**
     * Calls {@link #connectCore} and retries automatically on timeout, up to {@code retriesLeft}
     * additional times. The in-flight guard for the word stays held across retries; {@code connectCore}'s
     * {@code whenComplete} cleans up all per-word state on each attempt so each retry starts fresh.
     */
    private CompletableFuture<TauSyncStream> connectWithRetry(String wordTrimmed, int timeoutSec, int retriesLeft) {
        return connectCore(wordTrimmed, timeoutSec)
                .handle((stream, ex) -> {
                    if (ex == null) {
                        return CompletableFuture.completedFuture(stream);
                    }
                    Throwable cause = ex.getCause() != null ? ex.getCause() : ex;
                    if (cause instanceof java.util.concurrent.TimeoutException
                            && retriesLeft > 0 && !disposed) {
                        // connectCore's whenComplete already cleaned up service registry and word
                        // channel — safe to start a fresh attempt.
                        return connectWithRetry(wordTrimmed, timeoutSec, retriesLeft - 1);
                    }
                    CompletableFuture<TauSyncStream> failed = new CompletableFuture<>();
                    failed.completeExceptionally(ex);
                    return failed;
                })
                .thenCompose(f -> f);
    }

    /**
     * Runs the actual handshake for an already guard-acquired word.
     */
    private CompletableFuture<TauSyncStream> connectCore(String wordTrimmed, int timeoutSec) {
        LinkedBlockingQueue<TauSyncStream> wordChannel = getOrCreateWordChannel(wordTrimmed);
        registerWordListener(wordTrimmed, wordChannel);

        ConnectionContext ctx = ConnectionContext.getInstance();
        ConnectAttempt attempt = createConnectAttempt(ctx);

        return sendWordRequestAsync(wordTrimmed, attempt.localId)
                .thenCompose(ignored -> resolveConnectRaceAsync(ctx, wordChannel, attempt, timeoutSec, wordTrimmed))
                .whenComplete((stream, ex) -> {
                    // Unregister the service listener after the connection resolves (success or failure).
                    //
                    // Without this cleanup, the callback registered by registerWordListener stays in
                    // ConnectionContext.serviceRegistry after the first use. On a second transfer using
                    // the same word, the incoming REQ is handled directly (bypassing pendingDiscoveryByWord),
                    // so getPeerWaitingWords() never surfaces the word again and the app's polling loop
                    // cannot trigger a second connect() call — causing the desktop to hang forever.
                    ConnectionContext.getInstance().unregisterService(wordTrimmed);
                    // Remove the word channel (mirrors C# _incomingByWord.TryRemove). Without this,
                    // a stale stream offered after a timed-out attempt stayed queued and was handed
                    // to the NEXT connect(word) call, pairing it with dead routing state.
                    incomingByWord.remove(wordTrimmed);
                    if (ex != null) {
                        // Both race paths failed (typically a double timeout) — release the outgoing
                        // attempt's id/handler and close its stream. cleanup is idempotent, so it is
                        // safe even when the peer path already cleaned the attempt up.
                        cleanupLosingOutgoingAttempt(ctx, attempt, wordTrimmed);
                    }
                    // Release the in-flight guard last, so the word only becomes reusable after
                    // all per-word state (service registry, word channel) is torn down.
                    inFlightWords.remove(wordTrimmed);
                });
    }

    // ── Connect internals ─────────────────────────────────────────────

    private void validateConnectState(String word) {
        if (word == null || word.trim().isEmpty()) {
            throw new IllegalArgumentException("Word cannot be null or empty.");
        }
        if (primaryTransport == null || !primaryTransport.isConnected()) {
            throw new IllegalStateException("Transport not connected. connectTransport first.");
        }
        if (disposed) {
            throw new IllegalStateException("ConnectionManager is disposed.");
        }
    }

    private LinkedBlockingQueue<TauSyncStream> getOrCreateWordChannel(String wordKey) {
        return incomingByWord.computeIfAbsent(wordKey, k -> new LinkedBlockingQueue<>());
    }

    private void registerWordListener(String wordKey, LinkedBlockingQueue<TauSyncStream> channel) {
        ConnectionContext.getInstance().registerService(wordKey, (localId, peerSenderId, stream) ->
                handleWordRequest(wordKey, channel, localId, peerSenderId, stream));
    }

    private ConnectAttempt createConnectAttempt(ConnectionContext ctx) {
        int localId = ctx.reserveId();
        BackBufferedInputStream backStream = new BackBufferedInputStream();
        CompletableFuture<byte[]> responseFuture = new CompletableFuture<>();

        ctx.registerHandler(localId, (payload, flags) -> {
            if ((flags & CoreConfig.FLAG_CONTROL) != 0) {
                responseFuture.complete(payload != null ? payload : new byte[0]);
                return;
            }
            if (payload != null && payload.length > 0) {
                backStream.writeChunk(payload);
            }
            if ((flags & CoreConfig.FLAG_FIN) != 0) {
                backStream.complete();
            }
        });

        return new ConnectAttempt(localId, backStream, responseFuture);
    }

    /**
     * Resolves the simultaneous-connect race deterministically using the transport role:
     * TCP client prefers the outgoing (own REQ->OK) path,
     * TCP server prefers the incoming (peer REQ->service callback) path.
     * Falls back to the other path if the preferred one fails.
     *
     * @param timeoutSec how long to wait for the peer before giving up on each path
     */
    private CompletableFuture<TauSyncStream> resolveConnectRaceAsync(
            ConnectionContext ctx,
            LinkedBlockingQueue<TauSyncStream> channel,
            ConnectAttempt attempt,
            int timeoutSec,
            String word) {

        // Arm the own-path timeout HERE — at race start — so both paths share a single
        // wall-clock budget (mirrors the C# shared timeoutCts). Arming it lazily inside
        // the fallback branch let the server role wait peerPath(timeoutSec) +
        // ownPath(timeoutSec) = 2x the requested timeout, overrunning the caller's
        // outer .get(timeoutSec + 5) guard in sdk.TauSync.connect().
        CompletableFuture<TauSyncStream> ownPath =
                waitForOkAndBuildStreamAsync(attempt.responseFuture, ctx, attempt.localId, attempt.backStream)
                        .orTimeout(timeoutSec, TimeUnit.SECONDS);

        CompletableFuture<TauSyncStream> peerPath = CompletableFuture.supplyAsync(() -> {
            try {
                long deadlineNanos = System.nanoTime() + TimeUnit.SECONDS.toNanos(timeoutSec);
                while (!disposed) {
                    long remainingNanos = deadlineNanos - System.nanoTime();
                    if (remainingNanos <= 0) {
                        throw new RuntimeException(new TimeoutException("Peer path timed out"));
                    }
                    long pollMs = Math.min(500, TimeUnit.NANOSECONDS.toMillis(remainingNanos));
                    if (pollMs <= 0) pollMs = 1;
                    TauSyncStream stream = channel.poll(pollMs, TimeUnit.MILLISECONDS);
                    if (stream != null) return stream;
                }
                throw new RuntimeException(
                        new IllegalStateException("ConnectionManager disposed during handshake"));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new RuntimeException(e);
            }
        }, HANDSHAKE_POOL);

        // The meeting-word handshake runs over the primary transport (Wi-Fi in single mode,
        // Bluetooth in hybrid), so the race tiebreaker reads the primary's role, not the singleton
        // context's internal transport.
        boolean preferOwnPath = !primaryTransport.isServerMode();

        if (preferOwnPath) {
            return ownPath
                    .handle((stream, ex) -> {
                        if (ex == null) return CompletableFuture.completedFuture(stream);
                        cleanupLosingOutgoingAttempt(ctx, attempt, word);
                        return peerPath;
                    })
                    .thenCompose(f -> f);
        }

        return peerPath
                .handle((stream, ex) -> {
                    if (ex == null) {
                        cleanupLosingOutgoingAttempt(ctx, attempt, word);
                        return CompletableFuture.completedFuture(stream);
                    }
                    // ownPath's timeout was armed at race start, so this fallback expires at
                    // the same wall-clock deadline instead of granting a fresh budget.
                    return ownPath;
                })
                .thenCompose(f -> f);
    }

    /**
     * Tears down an outgoing connect attempt whose REQ ended up unused — either the
     * connect failed (timeout / double timeout) or it resolved via the peer path.
     *
     * <p>Besides the local cleanup, sends a best-effort CANCEL frame (spec §7.8) so the
     * peer removes the now-orphaned REQ from its pending-discovery queue — or, if the
     * peer already handshook it into an incoming channel, aborts that channel with a
     * synthetic FIN. Without the CANCEL, one-shot meeting words leak a "peer waiting"
     * entry on the peer for the rest of the session (re-reported by
     * {@code getPeerWaitingWords()} on every poll tick).
     */
    private void cleanupLosingOutgoingAttempt(ConnectionContext ctx, ConnectAttempt attempt, String word) {
        // One-shot: cleanup can run more than once for the same attempt (e.g. the
        // whenComplete failure path after a race branch already cleaned up) — the
        // CANCEL must be sent exactly once per abandoned REQ.
        if (attempt.cancelSent.compareAndSet(false, true)) {
            trySendWordCancel(word, attempt.localId);
        }
        ctx.releaseId(attempt.localId);
        ctx.unregisterHandler(attempt.localId);
        try {
            attempt.backStream.close();
        } catch (Exception ignored) {
        }
    }

    /**
     * Sends a best-effort CANCEL discovery frame for an abandoned REQ. Fire-and-forget:
     * failures are swallowed because cancellation is an optimisation (the transport may
     * already be dead, and an old peer simply drops unknown discovery statuses).
     */
    private void trySendWordCancel(String word, int localId) {
        try {
            TransferRequest cancel = new TransferRequest();
            cancel.setMagicBytes(CoreConfig.MAGIC_BYTES);
            cancel.setSenderID(localId);
            cancel.setType(word);
            cancel.setStatus("CANCEL");

            String json = gson.toJson(cancel);
            byte[] body = json.getBytes(StandardCharsets.UTF_8);
            byte[] frame = protocolHandler.buildFrame(CoreConfig.CONTROL_CHANNEL_ID, body, CoreConfig.FLAG_CONTROL);
            primaryTransport.sendRaw(frame);
        } catch (Exception ignored) {
            // Best-effort — never let a failed CANCEL break the connect cleanup path.
        }
    }

    private void handleWordRequest(String wordKey, LinkedBlockingQueue<TauSyncStream> channel,
                                   int localId, int peerSenderId, InputStream stream) {
        try {
            byte[] frame = buildOkFrame(wordKey, localId, peerSenderId);
            primaryTransport.sendRaw(frame).get();

            TauSyncStream duplex = new TauSyncStream(stream, localId, this);
            channel.offer(duplex);
        } catch (Exception ex) {
            ErrorListener listener = errorListener;
            if (listener != null) {
                listener.onError(ex instanceof Exception ? (Exception) ex : new RuntimeException(ex));
            }
        }
    }

    private byte[] buildOkFrame(String word, int localId, int peerSenderId) {
        TransferRequest ok = new TransferRequest();
        ok.setMagicBytes(CoreConfig.MAGIC_BYTES);
        ok.setSenderID(localId);
        ok.setType(word);
        ok.setStatus("OK");

        String json = gson.toJson(ok);
        byte[] body = json.getBytes(StandardCharsets.UTF_8);
        return protocolHandler.buildFrame(peerSenderId, body, CoreConfig.FLAG_CONTROL);
    }

    private CompletableFuture<Void> sendWordRequestAsync(String word, int localId) {
        TransferRequest request = new TransferRequest();
        request.setMagicBytes(CoreConfig.MAGIC_BYTES);
        request.setSenderID(localId);
        request.setType(word);
        request.setStatus("REQ");

        String json = gson.toJson(request);
        byte[] reqBody = json.getBytes(StandardCharsets.UTF_8);
        byte[] reqFrame = protocolHandler.buildFrame(CoreConfig.CONTROL_CHANNEL_ID, reqBody, CoreConfig.FLAG_CONTROL);
        return primaryTransport.sendRaw(reqFrame);
    }

    private CompletableFuture<TauSyncStream> waitForOkAndBuildStreamAsync(
            CompletableFuture<byte[]> responseTask,
            ConnectionContext ctx,
            int localId,
            BackBufferedInputStream backStream) {

        return responseTask.thenApply(payload -> {
            TransferRequest response = parseTransferResponse(payload);
            if (response == null || response.getStatus() == null
                    || !response.getStatus().trim().equalsIgnoreCase("OK")) {
                ctx.releaseId(localId);
                ctx.unregisterHandler(localId);
                try {
                    backStream.close();
                } catch (Exception ignored) {
                }
                throw new RuntimeException("Connect rejected by peer.");
            }
            ctx.setTargetForSend(localId, response.getSenderID());
            return new TauSyncStream(backStream, localId, this);
        });
    }

    // ── Stream Data ───────────────────────────────────────────────────

    /**
     * Returns the transport for a single send, routing by the explicit {@code preferWifi} flag. A
     * Wi-Fi send brings the link up on demand (running the WIFI_CONNECT handshake, or reviving a link
     * torn down for idle) and falls back to Bluetooth only if Wi-Fi cannot be established; a Bluetooth
     * send always uses the primary link. The chosen link is recorded as the stream's last-used
     * transport so its FIN follows the same socket (see {@link #completeStream}). Routing is per send
     * by design — a stream may use Bluetooth for one write and Wi-Fi for the next — but a single send
     * is never split across both links. Mirrors C# {@code ResolveSendTransport}.
     */
    private ITransport resolveSendTransport(int localId, boolean preferWifi) {
        if (hybrid == null)
            return primaryTransport;  // single transport (Wi-Fi-only or Bluetooth-only)

        ITransport chosen = preferWifi ? hybrid.acquireWifiOrFallback() : primaryTransport;

        // If this stream is switching the link it sends on, drain the old link first so its in-flight
        // data cannot be overtaken by the new (faster) link at the receiver.
        ITransport last = lastTransportByStream.get(localId);
        if (last != null && last != chosen && last.isConnected()) {
            barrierBeforeSwitch(localId, last);
        }

        lastTransportByStream.put(localId, chosen);
        return chosen;
    }

    /**
     * Drains the channel's {@code oldTransport} before the stream starts sending on a different link:
     * emits a BARRIER on the old link (so it is ordered after that link's data) and waits for the peer's
     * BARRIER_ACK. Best-effort — a missing ACK times out ({@link CoreConfig#BARRIER_ACK_TIMEOUT_MS}) and
     * the send proceeds rather than hanging.
     */
    private void barrierBeforeSwitch(int localId, ITransport oldTransport) {
        Integer peerId = ConnectionContext.getInstance().getPeerIdFor(localId);
        if (peerId == null) return;

        CompletableFuture<Void> ack = new CompletableFuture<>();
        pendingBarriers.put(localId, ack);
        try {
            byte[] frame = protocolHandler.buildFrame(peerId, new byte[0], CoreConfig.FLAG_BARRIER);
            oldTransport.sendRaw(frame).get();
            ack.get(CoreConfig.BARRIER_ACK_TIMEOUT_MS, TimeUnit.MILLISECONDS);
        } catch (Exception ignored) {
            // Timeout or send failure — proceed anyway (degrade to unordered, never hang).
        } finally {
            pendingBarriers.remove(localId);
        }
    }

    /**
     * Handles an inbound transport-switch barrier frame (dispatched out-of-band by
     * {@link ConnectionContext}). A BARRIER asks us to confirm we have drained this channel's data on
     * the link it arrived over: we reply BARRIER_ACK over the always-on Bluetooth primary (the ACK only
     * needs to arrive — its ordering versus data is irrelevant). A BARRIER_ACK completes the sender's
     * pending switch.
     */
    private void onChannelControl(int targetId, byte flags) {
        if ((flags & CoreConfig.FLAG_BARRIER_ACK) != 0) {
            CompletableFuture<Void> ack = pendingBarriers.get(targetId);
            if (ack != null) ack.complete(null);
            return;
        }
        if ((flags & CoreConfig.FLAG_BARRIER) != 0) {
            Integer peerId = ConnectionContext.getInstance().getPeerIdFor(targetId);
            if (peerId == null) return;
            byte[] frame = protocolHandler.buildFrame(peerId, new byte[0], CoreConfig.FLAG_BARRIER_ACK);
            primaryTransport.sendRaw(frame);  // fire-and-forget; never block the receive loop
        }
    }

    @Override
    public void sendStreamData(int localId, byte[] buffer, int offset, int count) {
        // No explicit hint (e.g. a raw getOutputStream() write): fall back to size — a payload at or
        // above a full wire chunk is treated as large and routed over Wi-Fi in hybrid mode.
        sendStreamData(localId, buffer, offset, count, count > CoreConfig.HYBRID_SMALL_THRESHOLD_BYTES);
    }

    @Override
    public void sendStreamData(int localId, byte[] buffer, int offset, int count, boolean preferWifi) {
        if (disposed) throw new IllegalStateException("ConnectionManager is disposed.");
        if (primaryTransport == null) throw new IllegalStateException("Transport not initialized.");
        if (buffer == null) throw new IllegalArgumentException("buffer must not be null");
        if (offset < 0 || count < 0 || offset + count > buffer.length) {
            throw new IndexOutOfBoundsException("Invalid offset/count");
        }
        if (count == 0) return;

        Integer peerId = ConnectionContext.getInstance().getPeerIdFor(localId);
        if (peerId == null) {
            throw new IllegalStateException(
                    "No peer route for localId " + localId
                            + ". Handshake may not have completed; do not write before connect(word) finishes.");
        }

        // Route this send to one transport (Wi-Fi when flagged, else Bluetooth) and send every wire
        // frame over it, so the send is never split across links and its frames stay ordered.
        ITransport transport = resolveSendTransport(localId, preferWifi);

        int sent = 0;
        while (sent < count) {
            int sliceLen = Math.min(CoreConfig.STREAM_CHUNK_SIZE, count - sent);
            byte[] chunk = new byte[sliceLen];
            System.arraycopy(buffer, offset + sent, chunk, 0, sliceLen);
            byte[] frame = protocolHandler.buildFrame(peerId, chunk, (byte) 0);
            try {
                transport.sendRaw(frame).get();
            } catch (Exception e) {
                throw new RuntimeException("Failed to send stream data", e);
            }
            sent += sliceLen;
        }
    }

    @Override
    public CompletableFuture<Void> sendStreamDataAsync(int localId, byte[] buffer, int offset, int count) {
        return sendStreamDataAsync(localId, buffer, offset, count,
                count > CoreConfig.HYBRID_SMALL_THRESHOLD_BYTES);
    }

    @Override
    public CompletableFuture<Void> sendStreamDataAsync(int localId, byte[] buffer, int offset, int count, boolean preferWifi) {
        if (disposed) {
            return CompletableFuture.failedFuture(new IllegalStateException("ConnectionManager is disposed."));
        }
        if (primaryTransport == null) {
            return CompletableFuture.failedFuture(new IllegalStateException("Transport not initialized."));
        }
        if (buffer == null) {
            return CompletableFuture.failedFuture(new IllegalArgumentException("buffer must not be null"));
        }
        if (offset < 0 || count < 0 || offset + count > buffer.length) {
            return CompletableFuture.failedFuture(new IndexOutOfBoundsException("Invalid offset/count"));
        }
        if (count == 0) return CompletableFuture.completedFuture(null);

        Integer peerId = ConnectionContext.getInstance().getPeerIdFor(localId);
        if (peerId == null) {
            return CompletableFuture.failedFuture(new IllegalStateException(
                    "No peer route for localId " + localId));
        }

        // Route this send to one transport and send every chunk over it (see sendStreamData).
        // Resolving only blocks while Wi-Fi is first being brought up; afterwards it returns immediately.
        final ITransport transport = resolveSendTransport(localId, preferWifi);

        List<byte[]> frames = new ArrayList<>();
        int sent = 0;
        while (sent < count) {
            int sliceLen = Math.min(CoreConfig.STREAM_CHUNK_SIZE, count - sent);
            byte[] chunk = new byte[sliceLen];
            System.arraycopy(buffer, offset + sent, chunk, 0, sliceLen);
            frames.add(protocolHandler.buildFrame(peerId, chunk, (byte) 0));
            sent += sliceLen;
        }
        CompletableFuture<Void> result = CompletableFuture.completedFuture(null);
        for (byte[] frame : frames) {
            result = result.thenCompose(ignored -> transport.sendRaw(frame));
        }
        return result;
    }

    @Override
    public void completeStream(int localId) {
        if (disposed) return;
        if (primaryTransport == null) return;

        Integer peerId = ConnectionContext.getInstance().getPeerIdFor(localId);
        if (peerId != null) {
            // Send FIN over the same link the stream last sent data on, so it cannot overtake that data
            // on the other transport. Falls back to primary for a stream that was never written (empty
            // close) or whose last link is gone (idle-disconnected and already drained).
            ITransport last = lastTransportByStream.get(localId);
            ITransport finTransport = (last != null && last.isConnected()) ? last : primaryTransport;
            byte[] finFrame = protocolHandler.buildFrame(peerId, new byte[0], CoreConfig.FLAG_FIN);
            try {
                finTransport.sendRaw(finFrame).get();
            } catch (Exception ignored) {
            }
        }
        lastTransportByStream.remove(localId);
        ConnectionContext.getInstance().releaseId(localId);
    }

    @Override
    public void setErrorListener(ErrorListener listener) {
        this.errorListener = listener;
    }

    // ── Lifecycle ─────────────────────────────────────────────────────

    @Override
    public void close() {
        if (disposed) return;
        disposed = true;
        incomingByWord.clear();
        if (hybrid != null) {
            // Hybrid: the manager owns its transports, so end the whole session here. Disconnecting
            // both decrements the ref-count to zero, which aborts channels and resets shared state.
            ConnectionContext.getInstance().unregisterSessionControlListener();
            ConnectionContext.getInstance().unregisterChannelControlListener();
            hybrid.dispose();
            // The secondary (Wi-Fi) transport is ConnectionContext's process-wide singleton
            // SocketTransport, reused across every session. disconnect() it (closes the socket but
            // keeps it reusable) — NOT close(), which sets disposed=true permanently and, because the
            // singleton is final and never recreated, makes every later connectTo() fail with
            // "Transport disposed". disconnect() still decrements the ref-count, so channels are
            // aborted and shared state is reset exactly as close() would have done.
            try {
                secondaryTransport.disconnect();
            } catch (Exception ignored) {
            }
            // The Bluetooth primary is created fresh per hybrid session, so a permanent close() is fine.
            try {
                primaryTransport.close();
            } catch (Exception ignored) {
            }
        }
    }

    /**
     * Snapshot of words the peer has fired REQ for but we have not yet paired
     * with locally. Mirrors C# {@code ConnectionManager.GetPeerWaitingWords}.
     */
    public java.util.List<String> getPeerWaitingWords() {
        return ConnectionContext.getInstance().getPeerWaitingWords();
    }

    // ── Helpers ───────────────────────────────────────────────────────

    private TransferRequest parseTransferResponse(byte[] payload) {
        if (payload == null || payload.length == 0) return null;
        try {
            String json = new String(payload, StandardCharsets.UTF_8);
            return gson.fromJson(json, TransferRequest.class);
        } catch (Exception e) {
            return null;
        }
    }

    private static final class ConnectAttempt {
        final int localId;
        final BackBufferedInputStream backStream;
        final CompletableFuture<byte[]> responseFuture;

        /**
         * One-shot guard so the CANCEL frame for this attempt's abandoned REQ is sent
         * exactly once, even when cleanup runs from more than one race/cleanup path.
         */
        final AtomicBoolean cancelSent = new AtomicBoolean(false);

        ConnectAttempt(int localId, BackBufferedInputStream backStream,
                       CompletableFuture<byte[]> responseFuture) {
            this.localId = localId;
            this.backStream = backStream;
            this.responseFuture = responseFuture;
        }
    }
}

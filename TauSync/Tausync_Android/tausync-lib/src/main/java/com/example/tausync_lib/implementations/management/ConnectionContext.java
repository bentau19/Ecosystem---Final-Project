package com.example.tausync_lib.implementations.management;

import com.example.tausync_lib.core.CoreConfig;
import com.example.tausync_lib.implementations.transport.SocketTransport;
import com.example.tausync_lib.interfaces.ITransport;
import com.example.tausync_lib.models.TransferRequest;
import com.google.gson.Gson;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BiConsumer;

/**
 * Central hub (singleton) for ID management and packet routing per TauSync v3.
 *
 * <p>Branches on TargetID: 0 = discovery (requires CONTROL + MagicBytes),
 * >0 = pass to registered handler. FIN cleanup: remove from both routingMap
 * and targetMap.
 *
 * <p>IDs are never reused within a session (24-bit monotonic counter, reset on
 * reconnect), so stale FIN frames addressed to a closed channel hit an unmapped
 * ID and are dropped instead of corrupting a newer channel that recycled the
 * same ID. Matches C# ConnectionContext.
 */
public final class ConnectionContext {

    private static final ConnectionContext INSTANCE = new ConnectionContext();

    public static ConnectionContext getInstance() {
        return INSTANCE;
    }

    private final AtomicInteger nextCorrelationId = new AtomicInteger(CoreConfig.MIN_ID);

    /** Guards the wrap-around increment in {@link #reserveId()} so two threads cannot both reset to MIN_ID and hand out a duplicate ID. */
    private final Object idLock = new Object();

    /**
     * LocalID -> handler(payload, flags). Handler decides DATA vs in-band CONTROL.
     */
    private final ConcurrentHashMap<Integer, BiConsumer<byte[], Byte>> routingMap = new ConcurrentHashMap<>();

    /**
     * LocalID -> PeerID. For sending: TargetID = targetMap.get(localId) in the TPack header.
     */
    private final ConcurrentHashMap<Integer, Integer> targetMap = new ConcurrentHashMap<>();

    /**
     * Meeting Word -> callback(localId, peerSenderId, stream).
     * Invoked when REQ arrives on TargetID=0.
     */
    private final ConcurrentHashMap<String, TriConsumer<Integer, Integer, InputStream>> serviceRegistry =
            new ConcurrentHashMap<>();

    /**
     * REQ payloads queued per word when a discovery frame arrives before
     * {@link #registerService} was called. Drained when the service registers.
     */
    private final ConcurrentHashMap<String, ConcurrentLinkedQueue<byte[]>> pendingDiscoveryByWord =
            new ConcurrentHashMap<>();

    private final SocketTransport wifiTransport;
    private final Gson gson = new Gson();

    private ConnectionContext() {
        wifiTransport = new SocketTransport();
    }

    /**
     * Establishes the transport connection with no timeout (waits indefinitely).
     *
     * @param targetId peer IP for client mode; null/empty for server mode
     * @throws IllegalStateException if already connected or not initialised
     */
    public void initializeTransports(String targetId) throws Exception {
        initializeTransports(targetId, null);
    }

    /**
     * Establishes the transport connection, giving up after the timeout.
     *
     * @param targetId       peer IP for client mode; null/empty for server mode
     * @param timeoutSeconds max seconds to wait for the connection; null = wait forever
     * @throws java.util.concurrent.TimeoutException if the timeout elapses before connecting
     * @throws IllegalStateException                 if already connected or not initialised
     */
    public void initializeTransports(String targetId, Integer timeoutSeconds) throws Exception {
        if (wifiTransport.isConnected()) {
            throw new IllegalStateException("Transport already connected.");
        }
        // Clear any routing/discovery state left over from a previous session before
        // re-establishing, so stale handlers and pending REQs are not replayed on the
        // new session's frames. Mirrors the C# ConnectionContext.InitializeTransports.
        reset();
        try {
            wifiTransport.connect(targetId, timeoutSeconds).get();
        } catch (java.util.concurrent.ExecutionException e) {
            // Unwrap so callers see TimeoutException (or the real cause) directly,
            // matching the C# GetAwaiter().GetResult() unwrapping behaviour.
            Throwable cause = e.getCause();
            if (cause instanceof Exception) throw (Exception) cause;
            throw e;
        }
    }

    public ITransport getWifiTransport() {
        return wifiTransport;
    }

    public SocketTransport getWifiTransportAsSocket() {
        return wifiTransport;
    }

    /**
     * Returns true when the underlying transport accepted a connection (server mode).
     * Used by ConnectionManager for the simultaneous-connect race tiebreaker.
     */
    public boolean isTransportServerMode() {
        return wifiTransport.isServerMode();
    }

    // ── ID Management ─────────────────────────────────────────────────

    /**
     * Reserves the next channel ID. IDs are strictly monotonic within a session —
     * never recycled — so frames that arrive late for a closed channel (e.g. a peer
     * FIN delayed behind bulk transfer data) can never be misrouted to a newer
     * channel. The 24-bit space (16.7M IDs) cannot realistically be exhausted in
     * one session, and {@link #reset()} restarts the counter on every reconnect.
     *
     * @return an ID in the range [MIN_ID..MAX_ID]
     */
    public int reserveId() {
        for (Integer key : releasedIds.keySet()) {
            if (releasedIds.remove(key) != null) {
                return key;
            }
        }

        synchronized (idLock) {
            int id = nextCorrelationId.get();
            int next = id + 1;
            if (next > CoreConfig.MAX_ID) next = CoreConfig.MIN_ID;
            nextCorrelationId.set(next);
            return id;
        }
    }

    /**
     * Releases ID: clears routing/target maps immediately. The ID itself is
     * intentionally NOT returned to a free pool — recycling IDs allowed a delayed
     * peer FIN (or a double release from FIN-dispatch + completeStream) to destroy
     * the routing/target entries of a newer channel that had re-reserved the same
     * ID, surfacing as "No peer route for localId N" on writes. Safe to call
     * multiple times for the same ID.
     */
    public void releaseId(int id) {
        if (id < CoreConfig.MIN_ID || id > CoreConfig.MAX_ID) return;
        routingMap.remove(id);
        targetMap.remove(id);
    }

    /**
     * PeerID to use when sending for this local ID. Returns null if not bound.
     */
    public Integer getPeerIdFor(int localId) {
        return targetMap.get(localId);
    }

    /**
     * Binds localId -> peerId for sending (e.g. after initiator receives OK).
     */
    public void setTargetForSend(int localId, int peerId) {
        if (localId < CoreConfig.MIN_ID || localId > CoreConfig.MAX_ID) return;
        targetMap.put(localId, peerId);
    }

    public void registerHandler(int correlationId, BiConsumer<byte[], Byte> handler) {
        if (handler == null) throw new IllegalArgumentException("handler must not be null");
        routingMap.put(correlationId, handler);
    }

    public void unregisterHandler(int correlationId) {
        routingMap.remove(correlationId);
    }

    /**
     * Registers a listener for a Meeting Word.
     * Callback receives (localId, peerSenderId, backingInputStream).
     */
    public void registerService(String word, TriConsumer<Integer, Integer, InputStream> callback) {
        if (word == null || word.trim().isEmpty()) {
            throw new IllegalArgumentException("Word cannot be null or empty.");
        }
        if (callback == null) throw new IllegalArgumentException("callback must not be null");
        String key = word.trim();
        serviceRegistry.put(key, callback);
        drainPendingDiscovery(key);
    }

    public void unregisterService(String word) {
        if (word == null || word.trim().isEmpty()) return;
        String key = word.trim();
        serviceRegistry.remove(key);
        pendingDiscoveryByWord.remove(key);
    }

    /**
     * Returns a snapshot of words the peer is waiting on but we have not paired
     * with locally. Mirrors C# {@code ConnectionContext.GetPeerWaitingWords}.
     * Empty queues (drained but never removed by {@link #drainPendingDiscovery})
     * are filtered out.
     */
    public java.util.List<String> getPeerWaitingWords() {
        java.util.List<String> result = new java.util.ArrayList<>();
        for (java.util.Map.Entry<String, ConcurrentLinkedQueue<byte[]>> entry : pendingDiscoveryByWord.entrySet()) {
            if (!entry.getValue().isEmpty()) {
                result.add(entry.getKey());
            }
        }
        return java.util.Collections.unmodifiableList(result);
    }

    public boolean hasHandlerFor(int id) {
        return routingMap.containsKey(id);
    }

    /**
     * Aborts every open channel by delivering a synthetic FIN to its registered handler.
     * Each handler responds to FIN by completing its backing {@link BackBufferedInputStream},
     * which unblocks any thread sitting in {@code read()} with EOF instead of hanging forever.
     *
     * <p>Must be called when the transport dies (receive loop exit / explicit disconnect):
     * without it, streams whose peer vanished without sending FIN (e.g. desktop closed
     * mid-transfer) block their readers indefinitely. Mirrors C# {@code AbortAllChannels}.
     */
    public void abortAllChannels() {
        for (java.util.Map.Entry<Integer, BiConsumer<byte[], Byte>> entry : routingMap.entrySet()) {
            try {
                entry.getValue().accept(new byte[0], CoreConfig.FLAG_FIN);
            } catch (Exception ignored) {
                // A failing handler must not prevent the remaining channels from being aborted.
            }
        }
        routingMap.clear();
        targetMap.clear();
    }

    /**
     * Clears all routing, service, and discovery state accumulated during a session.
     *
     * <p>Must be called before re-establishing a new connection so that stale handlers
     * and pending discovery frames from the previous session are not replayed on the
     * incoming frames of the new session.
     */
    public void reset() {
        routingMap.clear();
        targetMap.clear();
        serviceRegistry.clear();
        pendingDiscoveryByWord.clear();
        nextCorrelationId.set(CoreConfig.MIN_ID);
    }

    // ── Frame Dispatch ────────────────────────────────────────────────

    /**
     * Dispatches a received frame to the appropriate handler.
     *
     * @param targetId 0 for control/discovery, >0 for channel handler
     * @param payload  frame payload (maybe empty)
     * @param flags    frame flags bitmask
     * @return true if the frame was handled
     */
    public boolean dispatch(int targetId, byte[] payload, byte flags) {
        if (payload == null) payload = new byte[0];
        if (targetId > 0) {
            return dispatchToExistingChannel(targetId, payload, flags);
        }
        return dispatchDiscoveryRequest(payload, flags);
    }

    private boolean dispatchToExistingChannel(int targetId, byte[] payload, byte flags) {
        BiConsumer<byte[], Byte> handler = routingMap.get(targetId);
        if (handler == null) return false;

        handler.accept(payload, flags);

        if ((flags & CoreConfig.FLAG_FIN) != 0) {
            routingMap.remove(targetId);
            targetMap.remove(targetId);
            releaseId(targetId);
        }
        return true;
    }

    private boolean dispatchDiscoveryRequest(byte[] payload, byte flags) {
        if ((flags & CoreConfig.FLAG_CONTROL) == 0) return false;

        TransferRequest request = parseTransferRequest(payload);
        if (request == null) return false;
        if (request.getMagicBytes() != CoreConfig.MAGIC_BYTES) return false;
        if (request.getStatus() == null) return false;
        if (request.getStatus().trim().equalsIgnoreCase("CANCEL")) {
            // Peer abandoned an outgoing REQ (its connect timed out or resolved via the
            // peer path) — forget the orphan instead of reporting it forever. Spec §7.8.
            return handleDiscoveryCancel(request);
        }
        if (!request.getStatus().trim().equalsIgnoreCase("REQ")) return false;

        String word = request.getType() != null ? request.getType().trim() : null;
        if (word == null || word.isEmpty()) return false;

        TriConsumer<Integer, Integer, InputStream> callback = serviceRegistry.get(word);
        if (callback == null) {
            enqueuePendingDiscovery(word, payload);
            return true;
        }

        return completeDiscoveryHandshake(request, callback);
    }

    /**
     * Handles a peer handshake cancellation: the peer abandoned its REQ for
     * {@code (Type=word, SenderID)} and we must forget it. Two cases:
     *
     * <ol>
     *   <li><b>REQ still queued</b> — remove exactly the queued payload whose SenderID
     *       matches from {@link #pendingDiscoveryByWord}, so {@link #getPeerWaitingWords()}
     *       stops reporting a word nobody is waiting on (and the app's polling loop stops
     *       warning about it every tick).</li>
     *   <li><b>REQ already handshaken</b> — the incoming channel built from that REQ
     *       targets the cancelled SenderID. Abort it with a synthetic FIN (the
     *       {@link #abortAllChannels()} pattern) so any blocked reader gets EOF instead of
     *       hanging until its read timeout, then release the local id.</li>
     * </ol>
     *
     * <p>The reverse {@link #targetMap} lookup cannot hit a live winning channel: the
     * cancelled SenderID is a peer <em>outgoing</em>-attempt id, while our own outgoing
     * routes target the peer's <em>incoming</em> ids — distinct values from the peer's
     * monotonic id counter.
     *
     * <p>Idempotent and best-effort: a CANCEL for an unknown word/id is a no-op.
     */
    private boolean handleDiscoveryCancel(TransferRequest cancel) {
        String word = cancel.getType() != null ? cancel.getType().trim() : null;
        if (word == null || word.isEmpty()) return false;

        // ── Case 1: REQ still queued — drop the matching entry only ──────────────
        ConcurrentLinkedQueue<byte[]> queue = pendingDiscoveryByWord.get(word);
        if (queue != null) {
            java.util.Iterator<byte[]> it = queue.iterator();
            while (it.hasNext()) {
                byte[] entry = it.next();
                TransferRequest req = parseTransferRequest(entry);
                if (req != null
                        && req.getSenderID() == cancel.getSenderID()
                        && req.getStatus() != null
                        && req.getStatus().trim().equalsIgnoreCase("REQ")) {
                    it.remove();
                }
            }
            if (queue.isEmpty()) {
                pendingDiscoveryByWord.remove(word, queue);
            }
        }

        // ── Case 2: REQ already handshaken into an active incoming channel ────────
        for (java.util.Map.Entry<Integer, Integer> entry : targetMap.entrySet()) {
            if (entry.getValue() == null || entry.getValue() != cancel.getSenderID()) continue;
            BiConsumer<byte[], Byte> handler = routingMap.get(entry.getKey());
            if (handler != null) {
                try {
                    handler.accept(new byte[0], CoreConfig.FLAG_FIN);
                } catch (Exception ignored) {
                    // A failing handler must not prevent the id cleanup below.
                }
            }
            cleanupLocalId(entry.getKey());
            break;
        }

        return true;
    }

    private void enqueuePendingDiscovery(String word, byte[] payload) {
        ConcurrentLinkedQueue<byte[]> queue =
                pendingDiscoveryByWord.computeIfAbsent(word, k -> new ConcurrentLinkedQueue<>());

        byte[] copy = new byte[payload.length];
        System.arraycopy(payload, 0, copy, 0, payload.length);

        while (queue.size() >= CoreConfig.MAX_PENDING_DISCOVERY_PER_WORD) {
            queue.poll();
        }
        queue.offer(copy);
    }

    private void drainPendingDiscovery(String word) {
        ConcurrentLinkedQueue<byte[]> queue = pendingDiscoveryByWord.get(word);
        if (queue == null) return;

        byte[] payload;
        while ((payload = queue.poll()) != null) {
            if (payload.length == 0) continue;

            TransferRequest request = parseTransferRequest(payload);
            if (request == null) continue;
            if (request.getMagicBytes() != CoreConfig.MAGIC_BYTES) continue;
            if (request.getStatus() == null) continue;
            if (!request.getStatus().trim().equalsIgnoreCase("REQ")) continue;

            TriConsumer<Integer, Integer, InputStream> callback = serviceRegistry.get(word);
            if (callback == null) continue;

            completeDiscoveryHandshake(request, callback);
        }
    }

    private boolean completeDiscoveryHandshake(TransferRequest request,
                                               TriConsumer<Integer, Integer, InputStream> callback) {
        int localId = reserveId();
        targetMap.put(localId, request.getSenderID());

        BackBufferedInputStream backStream = new BackBufferedInputStream();
        routingMap.put(localId, createIncomingChannelHandler(localId, backStream));

        scheduleServiceCallback(callback, localId, request.getSenderID(), backStream);
        return true;
    }

    private BiConsumer<byte[], Byte> createIncomingChannelHandler(int localId,
                                                                  BackBufferedInputStream stream) {
        return (payload, flags) -> {
            if (payload != null && payload.length > 0) {
                stream.writeChunk(payload);
            }
            if ((flags & CoreConfig.FLAG_FIN) != 0) {
                stream.complete();
                cleanupLocalId(localId);
            }
        };
    }

    private void scheduleServiceCallback(TriConsumer<Integer, Integer, InputStream> callback,
                                         int localId, int peerSenderId,
                                         BackBufferedInputStream stream) {
        Thread callbackThread = new Thread(() -> {
            try {
                callback.accept(localId, peerSenderId, stream);
            } catch (Exception e) {
                cleanupLocalId(localId);
                try {
                    stream.close();
                } catch (Exception ignored) {
                }
            }
        }, "TauSync-ServiceCb-" + localId);
        callbackThread.setDaemon(true);
        callbackThread.start();
    }

    private void cleanupLocalId(int localId) {
        routingMap.remove(localId);
        targetMap.remove(localId);
        releaseId(localId);
    }

    private TransferRequest parseTransferRequest(byte[] payload) {
        if (payload == null || payload.length == 0) return null;
        try {
            String json = new String(payload, StandardCharsets.UTF_8);
            return gson.fromJson(json, TransferRequest.class);
        } catch (Exception e) {
            return null;
        }
    }

    // ── Functional interface for service callbacks ─────────────────────

    /**
     * A three-argument consumer, used for service callbacks:
     * (localId, peerSenderId, backingInputStream).
     */
    @FunctionalInterface
    public interface TriConsumer<A, B, C> {
        void accept(A a, B b, C c);
    }
}

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
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BiConsumer;

/**
 * Central hub (singleton) for ID management and packet routing per TauSync v3.
 *
 * <p>Branches on TargetID: 0 = discovery (requires CONTROL + MagicBytes),
 * >0 = pass to registered handler. FIN cleanup: remove from both routingMap
 * and targetMap, then releaseId with delayed recycling.
 * Matches C# ConnectionContext.
 */
public final class ConnectionContext {

    private static final ConnectionContext INSTANCE = new ConnectionContext();

    public static ConnectionContext getInstance() {
        return INSTANCE;
    }

    private final AtomicInteger nextCorrelationId = new AtomicInteger(CoreConfig.MIN_ID);

    /**
     * IDs eligible for reuse. Uses ConcurrentHashMap as a set (value is always 0)
     * for idempotent add — safe when both FIN-dispatch and completeStream release
     * the same ID.
     */
    private final ConcurrentHashMap<Integer, Byte> releasedIds = new ConcurrentHashMap<>();

    private final ScheduledExecutorService recycleScheduler =
            Executors.newSingleThreadScheduledExecutor(r -> {
                Thread t = new Thread(r, "TauSync-IdRecycler");
                t.setDaemon(true);
                return t;
            });

    /** LocalID -> handler(payload, flags). Handler decides DATA vs in-band CONTROL. */
    private final ConcurrentHashMap<Integer, BiConsumer<byte[], Byte>> routingMap = new ConcurrentHashMap<>();

    /** LocalID -> PeerID. For sending: TargetID = targetMap.get(localId) in the TPack header. */
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
     * Establishes the transport connection.
     *
     * @param targetId peer IP for client mode; null/empty for server mode
     * @throws IllegalStateException if already connected or not initialised
     */
    public void initializeTransports(String targetId) throws Exception {
        if (wifiTransport.isConnected()) {
            throw new IllegalStateException("Transport already connected.");
        }
        wifiTransport.connect(targetId).get();
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
     * Reserves the next available ID, preferring recycled IDs.
     *
     * @return an ID in the range [MIN_ID..MAX_ID]
     */
    public int reserveId() {
        for (Integer key : releasedIds.keySet()) {
            if (releasedIds.remove(key) != null) {
                return key;
            }
        }

        int id = nextCorrelationId.getAndIncrement();
        if (id < CoreConfig.MIN_ID || id > CoreConfig.MAX_ID) {
            nextCorrelationId.set(CoreConfig.MIN_ID + 1);
            id = CoreConfig.MIN_ID;
        }
        return id;
    }

    /**
     * Releases ID: clears routing/target maps immediately, then schedules the ID
     * for recycling after {@link CoreConfig#ID_RECYCLE_DELAY_MS} so that in-flight
     * FIN frames are processed before another handler can claim the same ID.
     */
    public void releaseId(int id) {
        if (id < CoreConfig.MIN_ID || id > CoreConfig.MAX_ID) return;
        routingMap.remove(id);
        targetMap.remove(id);
        recycleScheduler.schedule(() -> releasedIds.put(id, (byte) 0),
                CoreConfig.ID_RECYCLE_DELAY_MS, TimeUnit.MILLISECONDS);
    }

    /** PeerID to use when sending for this local ID. Returns null if not bound. */
    public Integer getPeerIdFor(int localId) {
        return targetMap.get(localId);
    }

    /** Binds localId -> peerId for sending (e.g. after initiator receives OK). */
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
        String key = word.trim().toUpperCase();
        serviceRegistry.put(key, callback);
        drainPendingDiscovery(key);
    }

    public void unregisterService(String word) {
        if (word == null || word.trim().isEmpty()) return;
        String key = word.trim().toUpperCase();
        serviceRegistry.remove(key);
        pendingDiscoveryByWord.remove(key);
    }

    public boolean hasHandlerFor(int id) {
        return routingMap.containsKey(id);
    }

    // ── Frame Dispatch ────────────────────────────────────────────────

    /**
     * Dispatches a received frame to the appropriate handler.
     *
     * @param targetId 0 for control/discovery, >0 for channel handler
     * @param payload  frame payload (may be empty)
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
        if (!request.getStatus().trim().equalsIgnoreCase("REQ")) return false;

        String word = request.getType() != null ? request.getType().trim().toUpperCase() : null;
        if (word == null || word.isEmpty()) return false;

        TriConsumer<Integer, Integer, InputStream> callback = serviceRegistry.get(word);
        if (callback == null) {
            enqueuePendingDiscovery(word, payload);
            return true;
        }

        return completeDiscoveryHandshake(request, callback);
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
                try { stream.close(); } catch (Exception ignored) {}
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

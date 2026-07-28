package com.example.tausync_lib.implementations.management;

import com.example.tausync_lib.core.CoreConfig;
import com.example.tausync_lib.implementations.protocol.ProtocolHandler;
import com.example.tausync_lib.implementations.security.SecuritySession;
import com.example.tausync_lib.implementations.transport.SocketTransport;
import com.example.tausync_lib.interfaces.IProtocolHandler;
import com.example.tausync_lib.interfaces.ITransport;
import com.example.tausync_lib.models.KeyExchangeMessage;
import com.example.tausync_lib.models.SessionControlMessage;
import com.example.tausync_lib.models.TransferRequest;
import com.google.gson.Gson;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BiConsumer;
import java.util.function.Consumer;

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

    /**
     * Number of transports currently brought up by the app (intentional connects minus
     * intentional disconnects). Unexpected drops do NOT change this count — they reconnect
     * under the hood — so the session only ends when the last transport is explicitly
     * disconnected. See {@link #notifyTransportDisconnected()}.
     */
    private final AtomicInteger activeTransportCount = new AtomicInteger(0);

    /**
     * Hybrid session token. Generated server-side after the BT_MAGIC exchange and shared with
     * the client inside WIFI_CONNECT_READY; the client echoes it in SESSION_JOIN so the server
     * can prove the incoming Wi-Fi socket belongs to the same session as the Bluetooth link.
     * Null until a hybrid session is established; cleared by {@link #reset()}.
     */
    private volatile String sessionToken = null;

    /**
     * The peer's Wi-Fi IPv4 address, learned from the WifiHost field of the peer's BT_MAGIC frame
     * during the hybrid handshake. Lets the app connect Wi-Fi (or display/pre-fill the address)
     * without the user typing an IP — the Bluetooth link discovers it. Null until a hybrid BT_MAGIC
     * carrying a host arrives; cleared by {@link #reset()}.
     */
    private volatile String peerWifiHost = null;

    /**
     * The Bluetooth (primary) transport of an active hybrid session, registered by the hybrid
     * {@link ConnectionManager} when it connects. Lets a secondary manager from {@code newManager()}
     * bind to the always-on Bluetooth link instead of the lazy (usually disconnected) Wi-Fi socket
     * while a hybrid session is up — without it, {@code newManager().connect(word)} fails with
     * "Transport not connected". Unlike {@link #wifiTransport} it is not created here (the Android
     * {@link com.example.tausync_lib.implementations.transport.BluetoothTransport} needs a Context),
     * so it is registered after connect and cleared by {@link #reset()}.
     */
    private volatile ITransport bluetoothTransport = null;

    /**
     * True while the PC operator's connection approval is in progress (the server sent
     * APPROVAL_PENDING and has not yet answered with its BT_MAGIC or SESSION_REJECT). The app layer
     * reads this to keep its connect attempt alive for the full approval window instead of applying
     * its normal short timeout. Cleared by {@link #reset()}.
     */
    private volatile boolean approvalPending = false;

    /**
     * Per-session crypto: runs the ECDH key exchange and encrypts/decrypts frame payloads once a
     * shared key is derived. Same lifecycle as {@link #sessionToken} — cleared by {@link #reset()}.
     */
    private final SecuritySession securitySession = new SecuritySession();

    /** Completed when the peer's KEY_EXCHANGE public key arrives, unblocking {@link #completeKeyExchange}. */
    private volatile CompletableFuture<String> peerKeyReceived;

    /** Our ephemeral ECDH public key (base64 SPKI) for the in-flight exchange. */
    private volatile String localPublicKey;

    /** Builds the (plaintext) KEY_EXCHANGE frame; framing only, no routing state. */
    private final IProtocolHandler keyExchangeProtocol = new ProtocolHandler();

    private ConnectionContext() {
        wifiTransport = new SocketTransport();
    }

    /** True once the ECDH exchange has derived a key and payload encryption is active. */
    public boolean isEncryptionActive() {
        return securitySession.isEncryptionActive();
    }

    /** Encrypts a frame payload (no-op while inactive or empty). Called from {@link ProtocolHandler#buildFrame}. */
    public byte[] encryptPayload(byte[] payload) {
        return securitySession.encryptPayload(payload);
    }

    /** Decrypts a frame payload (no-op while inactive or empty). Called from {@link #dispatch} after routing. */
    public byte[] decryptPayload(byte[] payload) {
        return securitySession.decryptPayload(payload);
    }

    /**
     * Generates the local ECDH key pair and arms the peer-key awaiter. Call right after {@link #reset()}
     * and BEFORE the transport connects, so a peer KEY_EXCHANGE that arrives immediately can be completed
     * synchronously on the receive thread (closing the race where the peer's first encrypted frame is
     * processed before encryption activates).
     */
    public void beginKeyExchange() {
        peerKeyReceived = new CompletableFuture<>();
        localPublicKey = securitySession.generateLocalPublicKey();
    }

    /**
     * Sends our KEY_EXCHANGE public key over {@code transport} and awaits the peer's, then derives the
     * shared key. The exchange is symmetric (both sides send and receive) and runs as the very first
     * traffic on the primary transport, before BT_MAGIC / meeting-word discovery. Idempotent with the
     * synchronous derivation done in {@link #tryHandleKeyExchange}.
     */
    public void completeKeyExchange(ITransport transport) throws Exception {
        if (transport == null) throw new IllegalArgumentException("transport must not be null");
        if (peerKeyReceived == null) beginKeyExchange();
        CompletableFuture<String> awaiter = peerKeyReceived;

        KeyExchangeMessage message = new KeyExchangeMessage();
        message.setMagicBytes(CoreConfig.MAGIC_BYTES);
        message.setType(KeyExchangeMessage.TYPE_KEY_EXCHANGE);
        message.setPublicKey(localPublicKey);
        byte[] body = gson.toJson(message).getBytes(StandardCharsets.UTF_8);
        byte[] frame = keyExchangeProtocol.buildFrame(CoreConfig.CONTROL_CHANNEL_ID, body, CoreConfig.FLAG_CONTROL);
        transport.sendRaw(frame).get();

        String peerKey = awaiter.get(CoreConfig.KEY_EXCHANGE_TIMEOUT_MS, TimeUnit.MILLISECONDS);
        // Safety net: the dispatch path normally derives the key synchronously when the peer frame
        // arrives. completeExchange is idempotent, so this is a no-op if that already happened.
        securitySession.completeExchange(peerKey);
    }

    /** Stores the hybrid session token (see {@link #sessionToken}). */
    public void setSessionToken(String token) {
        this.sessionToken = token;
    }

    /** Returns the hybrid session token, or null if no hybrid session is established. */
    public String getSessionToken() {
        return sessionToken;
    }

    /** Stores the peer's Wi-Fi IPv4 address learned over Bluetooth (see {@link #peerWifiHost}). */
    public void setPeerWifiHost(String host) {
        this.peerWifiHost = host;
    }

    /** Returns the peer's Wi-Fi IPv4 address learned over Bluetooth, or null if not yet known. */
    public String getPeerWifiHost() {
        return peerWifiHost;
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
        // Wi-Fi-only mode: this is the session's ONLY link, so an unexpected drop must silently
        // reconnect (a prior hybrid session may have left auto-reconnect disabled on the singleton).
        wifiTransport.setAutoReconnect(true);
        // Arm the key exchange before connecting so a peer KEY_EXCHANGE arriving the instant the link
        // is up is captured (and derived synchronously) rather than lost.
        beginKeyExchange();
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

    /** Registers the active hybrid session's Bluetooth transport (see {@link #bluetoothTransport}). */
    public void setBluetoothTransport(ITransport transport) {
        this.bluetoothTransport = transport;
    }

    /** @return the active hybrid session's Bluetooth transport, or null in Wi-Fi-only mode. */
    public ITransport getBluetoothTransport() {
        return bluetoothTransport;
    }

    /** Records whether the PC operator's connection approval is in progress (see {@link #approvalPending}). */
    public void setApprovalPending(boolean pending) {
        this.approvalPending = pending;
    }

    /** @return true while the PC operator's connection approval is in progress. */
    public boolean isApprovalPending() {
        return approvalPending;
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
     * Records that a transport has been intentionally brought up. Paired with
     * {@link #notifyTransportDisconnected()} on the matching explicit disconnect.
     * Reconnects after an unexpected drop do NOT call this — the transport never
     * logically left the session.
     */
    public void notifyTransportConnected() {
        activeTransportCount.incrementAndGet();
    }

    /**
     * Records that a transport has been intentionally torn down. Only when the LAST live
     * transport disconnects (count reaches zero) are the open channels aborted and the
     * session state reset. Disconnecting one transport while another stays up (e.g. dropping
     * Wi-Fi but keeping Bluetooth) leaves that transport's channels untouched.
     */
    public void notifyTransportDisconnected() {
        if (activeTransportCount.decrementAndGet() <= 0) {
            abortAllChannels();
            reset();
        }
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
        sessionToken = null;
        peerWifiHost = null;
        bluetoothTransport = null;
        approvalPending = false;
        securitySession.clear();
        peerKeyReceived = null;
        localPublicKey = null;
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
        // Transport-switch barrier frames (BARRIER / BARRIER_ACK) are handled out-of-band by the hybrid
        // manager — they carry no channel data and must not trigger FIN cleanup.
        if ((flags & (CoreConfig.FLAG_BARRIER | CoreConfig.FLAG_BARRIER_ACK)) != 0) {
            BiConsumer<Integer, Byte> listener = channelControlListener;
            if (listener != null) listener.accept(targetId, flags);
            return true;
        }

        BiConsumer<byte[], Byte> handler = routingMap.get(targetId);
        if (handler == null) return false;

        // Decrypt only now — after the plaintext-header routing decision picked this handler — so
        // decryption is never on the routing path and dropped/empty frames cost nothing.
        payload = securitySession.decryptPayload(payload);
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

        // Key-exchange frames arrive in plaintext, before encryption is active, as the first traffic on
        // the link. Consume them here (gated on !active so a later decrypted control frame can never be
        // mistaken for one) BEFORE any decryption, and derive the key synchronously on this receive
        // thread so the peer's first encrypted frame is never processed before activation.
        if (!securitySession.isEncryptionActive() && tryHandleKeyExchange(payload)) return true;
        // Now that the key exchange has been ruled out, decrypt the control payload (no-op while inactive
        // or empty) before parsing its JSON.
        payload = securitySession.decryptPayload(payload);

        // Hybrid session signaling (BT_MAGIC, WIFI_CONNECT_*, SESSION_JOIN*) is checked before
        // meeting-word discovery: it shares TargetID=0 + CONTROL but is keyed by a reserved Type,
        // so it never collides with a user meeting word.
        if (tryHandleSessionControl(payload)) return true;

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

    // ── Hybrid session control ────────────────────────────────────────

    /**
     * Hybrid session-control callback. Registered by the hybrid {@link ConnectionManager};
     * invoked for every recognised session-control frame (BT_MAGIC, WIFI_CONNECT_*, SESSION_JOIN*)
     * arriving on TargetID=0. The coordinator infers the source transport from the message type,
     * so the source need not be passed here.
     */
    private volatile Consumer<SessionControlMessage> sessionControlListener;

    /** Registers the hybrid session-control callback (see {@link #sessionControlListener}). */
    public void registerSessionControlListener(Consumer<SessionControlMessage> listener) {
        if (listener == null) throw new IllegalArgumentException("listener must not be null");
        this.sessionControlListener = listener;
    }

    /** Clears the hybrid session-control callback (e.g. on manager close). */
    public void unregisterSessionControlListener() {
        this.sessionControlListener = null;
    }

    /**
     * Channel-control callback for transport-switch barrier frames (BARRIER / BARRIER_ACK) arriving on
     * a channel TargetID. Registered by the hybrid {@link ConnectionManager}; receives
     * (channelTargetId, flags). Lets the manager answer the barrier and complete pending switches
     * without the frame being treated as channel data.
     */
    private volatile BiConsumer<Integer, Byte> channelControlListener;

    /** Registers the channel-control (barrier) callback (see {@link #channelControlListener}). */
    public void registerChannelControlListener(BiConsumer<Integer, Byte> listener) {
        if (listener == null) throw new IllegalArgumentException("listener must not be null");
        this.channelControlListener = listener;
    }

    /** Clears the channel-control (barrier) callback (e.g. on manager close). */
    public void unregisterChannelControlListener() {
        this.channelControlListener = null;
    }

    /**
     * Routes a recognised session-control frame to the registered listener. Returns false (so the
     * frame falls through to meeting-word discovery) when no listener is registered or the payload
     * is not a valid session-control message.
     */
    private boolean tryHandleSessionControl(byte[] payload) {
        Consumer<SessionControlMessage> listener = sessionControlListener;
        if (listener == null) return false;
        SessionControlMessage message = parseSessionControl(payload);
        if (message == null) return false;
        listener.accept(message);
        return true;
    }

    /**
     * Consumes a plaintext KEY_EXCHANGE frame: derives the shared key synchronously (on the receive
     * thread, so encryption is active before the next frame is read) and unblocks
     * {@link #completeKeyExchange}. Returns false for any non-KEY_EXCHANGE payload so it falls through
     * to the normal discovery path.
     */
    private boolean tryHandleKeyExchange(byte[] payload) {
        KeyExchangeMessage message = parseKeyExchange(payload);
        if (message == null || message.getPublicKey() == null || message.getPublicKey().isEmpty()) {
            return false;
        }
        try {
            // Derive now if our key pair is ready (it is, after beginKeyExchange ran before connect).
            securitySession.completeExchange(message.getPublicKey());
        } catch (Exception ignored) {
            // Key pair not ready yet or malformed peer key — the driver's await + completeExchange safety
            // net will derive it. Never let a bad frame break dispatch.
        }
        CompletableFuture<String> awaiter = peerKeyReceived;
        if (awaiter != null) awaiter.complete(message.getPublicKey());
        return true;
    }

    private KeyExchangeMessage parseKeyExchange(byte[] payload) {
        if (payload == null || payload.length == 0) return null;
        try {
            KeyExchangeMessage message =
                    gson.fromJson(new String(payload, StandardCharsets.UTF_8), KeyExchangeMessage.class);
            if (message == null || message.getMagicBytes() != CoreConfig.MAGIC_BYTES) return null;
            return KeyExchangeMessage.TYPE_KEY_EXCHANGE.equals(message.getType()) ? message : null;
        } catch (Exception e) {
            return null;
        }
    }

    private SessionControlMessage parseSessionControl(byte[] payload) {
        if (payload == null || payload.length == 0) return null;
        try {
            SessionControlMessage message =
                    gson.fromJson(new String(payload, StandardCharsets.UTF_8), SessionControlMessage.class);
            if (message == null || message.getMagicBytes() != CoreConfig.MAGIC_BYTES) return null;
            return isKnownSessionType(message.getType()) ? message : null;
        } catch (Exception e) {
            return null;
        }
    }

    private static boolean isKnownSessionType(String type) {
        return SessionControlMessage.TYPE_BT_MAGIC.equals(type)
                || SessionControlMessage.TYPE_WIFI_CONNECT_REQ.equals(type)
                || SessionControlMessage.TYPE_WIFI_CONNECT_READY.equals(type)
                || SessionControlMessage.TYPE_SESSION_JOIN.equals(type)
                || SessionControlMessage.TYPE_SESSION_JOIN_ACK.equals(type)
                || SessionControlMessage.TYPE_SESSION_REJECT.equals(type)
                || SessionControlMessage.TYPE_SESSION_CONFIRM.equals(type)
                || SessionControlMessage.TYPE_APPROVAL_PENDING.equals(type)
                || SessionControlMessage.TYPE_WIFI_IDLE_CLOSE.equals(type);
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

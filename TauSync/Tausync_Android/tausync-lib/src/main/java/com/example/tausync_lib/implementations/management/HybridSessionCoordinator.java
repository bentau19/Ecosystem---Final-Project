package com.example.tausync_lib.implementations.management;

import com.example.tausync_lib.core.CoreConfig;
import com.example.tausync_lib.implementations.protocol.ProtocolHandler;
import com.example.tausync_lib.implementations.transport.SocketTransport;
import com.example.tausync_lib.implementations.util.NetworkUtils;
import com.example.tausync_lib.interfaces.IProtocolHandler;
import com.example.tausync_lib.interfaces.ITransport;
import com.example.tausync_lib.models.SessionControlMessage;
import com.google.gson.Gson;

import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Owns the Bluetooth↔Wi-Fi session for a hybrid {@link ConnectionManager}. Bluetooth is the
 * always-on primary link carrying control traffic and small payloads; Wi-Fi is brought up lazily
 * the first time a large payload needs it and torn down again after it sits idle.
 *
 * <p>Flow (see Bluetooth_Transport_Plan.md §2.1): after BT connects both sides exchange BT_MAGIC and
 * the server mints a session token. When a large payload is queued, the side that needs Wi-Fi asks
 * for it (client → WIFI_CONNECT_REQ; the server starts its TCP listener and replies
 * WIFI_CONNECT_READY with the token + address); the client connects TCP and sends SESSION_JOIN; the
 * server verifies the token and replies SESSION_JOIN_ACK. The Bluetooth role fixes the Wi-Fi role:
 * BT server = Wi-Fi server.
 *
 * <p>The coordinator never owns the channel routing maps — those live in the shared
 * {@link ConnectionContext} singleton, so a channel works over whichever transport carried its
 * frames.
 *
 * <p>Matches C# HybridSessionCoordinator.
 */
final class HybridSessionCoordinator {

    private final ITransport bluetooth;       // primary: control + small data, always connected
    private final SocketTransport wifi;       // secondary: large data only, lazy
    private final IProtocolHandler protocolHandler;
    private final Gson gson = new Gson();

    /** Guards every transition of the Wi-Fi state machine (wifiUp / wifiReady / wifiActivating). */
    private final Object wifiLock = new Object();

    private volatile boolean isServer;
    private volatile boolean disposed;

    /** Completed when the peer's BT_MAGIC arrives, unblocking {@link #startBtSession()}. */
    private volatile CompletableFuture<Void> peerMagicReceived = new CompletableFuture<>();

    /** Completed when Wi-Fi is usable for sending (server: SESSION_JOIN verified; client: ACK received). */
    private CompletableFuture<Void> wifiReady = new CompletableFuture<>();

    private boolean wifiUp;
    private boolean wifiActivating;
    private ScheduledExecutorService idleTimer;

    private static final int IDLE_CHECK_PERIOD_MS = 5_000;

    HybridSessionCoordinator(ITransport bluetooth, SocketTransport wifi, IProtocolHandler protocolHandler) {
        if (bluetooth == null) throw new IllegalArgumentException("bluetooth must not be null");
        if (wifi == null) throw new IllegalArgumentException("wifi must not be null");
        this.bluetooth = bluetooth;
        this.wifi = wifi;
        this.protocolHandler = protocolHandler != null ? protocolHandler : new ProtocolHandler();
    }

    /**
     * Runs the BT_MAGIC exchange after the Bluetooth link is up: both sides send their magic and
     * wait for the peer's, then the server mints the session token. Must be called once, right after
     * the Bluetooth transport connects. Blocks until the exchange completes or times out.
     */
    void startBtSession() throws Exception {
        isServer = bluetooth.isServerMode();
        peerMagicReceived = new CompletableFuture<>();

        // BT_MAGIC carries our own Wi-Fi IP so the peer can reach us over Wi-Fi (or just display the
        // address) without anyone typing it in: the Bluetooth link discovers it for them.
        SessionControlMessage magic = newMessage(SessionControlMessage.TYPE_BT_MAGIC);
        magic.setWifiHost(NetworkUtils.getLocalWifiIpAddress());
        magic.setWifiPort(CoreConfig.DEFAULT_PORT);
        sendOverBluetooth(magic).get();
        peerMagicReceived.get(CoreConfig.BT_CONNECT_TIMEOUT_MS, TimeUnit.MILLISECONDS);

        if (isServer) {
            ConnectionContext.getInstance().setSessionToken(UUID.randomUUID().toString());
        }
    }

    /**
     * Picks the transport for a logical send of {@code payloadBytes} bytes. Small payloads always go
     * over Bluetooth. A large payload brings Wi-Fi up on demand and waits for it; if Wi-Fi cannot be
     * established in time it falls back to Bluetooth (degraded, but the data still flows).
     */
    ITransport transportForSend(int payloadBytes) {
        if (payloadBytes <= CoreConfig.HYBRID_SMALL_THRESHOLD_BYTES) {
            return bluetooth;
        }
        return acquireWifiOrFallback();
    }

    /**
     * Brings Wi-Fi up (running the WIFI_CONNECT handshake if needed) and waits for it to become
     * usable, returning the Wi-Fi transport on success. If Wi-Fi cannot be established within the
     * retry budget it falls back to Bluetooth so the send still succeeds — degraded but reliable.
     * Used both for the first large send on a stream and to revive a stream's Wi-Fi link after an
     * idle teardown.
     */
    ITransport acquireWifiOrFallback() {
        if (wifiUp && wifi.isConnected()) {
            return wifi;
        }

        for (int attempt = 0; attempt < CoreConfig.WIFI_RECONNECT_MAX_ATTEMPTS && !disposed; attempt++) {
            triggerWifiConnect();
            CompletableFuture<Void> gate;
            synchronized (wifiLock) {
                gate = wifiReady;
            }
            try {
                gate.get(CoreConfig.BT_CONNECT_TIMEOUT_MS, TimeUnit.MILLISECONDS);
                return wifi;
            } catch (java.util.concurrent.TimeoutException e) {
                // Timed out — if the bring-up failed it already reset wifiActivating, so
                // triggerWifiConnect restarts on the next iteration.
            } catch (Exception e) {
                break; // unexpected error — skip remaining retries
            }
        }
        // All retries exhausted — fall back to Bluetooth so the send still succeeds.
        return bluetooth;
    }

    /** Routes a recognised session-control frame. Registered with the shared context dispatcher. */
    void onSessionControl(SessionControlMessage message) {
        String type = message.getType();
        if (SessionControlMessage.TYPE_BT_MAGIC.equals(type)) {
            // Remember the peer's Wi-Fi address so the app can reach it (or pre-fill the IP field)
            // without manual entry. The peer's BT_MAGIC is the earliest we learn it.
            String host = message.getWifiHost();
            if (host != null && !host.trim().isEmpty()) {
                ConnectionContext.getInstance().setPeerWifiHost(host);
            }
            peerMagicReceived.complete(null);
        } else if (SessionControlMessage.TYPE_WIFI_CONNECT_REQ.equals(type)) {
            if (isServer) triggerWifiConnect();
        } else if (SessionControlMessage.TYPE_WIFI_CONNECT_READY.equals(type)) {
            if (!isServer) handleWifiConnectReady(message);
        } else if (SessionControlMessage.TYPE_SESSION_JOIN.equals(type)) {
            if (isServer) handleSessionJoin(message);
        } else if (SessionControlMessage.TYPE_SESSION_JOIN_ACK.equals(type)) {
            if (!isServer) markWifiReady();
        }
    }

    void dispose() {
        disposed = true;
        ScheduledExecutorService timer = idleTimer;
        if (timer != null) timer.shutdownNow();
        idleTimer = null;
    }

    // ── Wi-Fi bring-up ────────────────────────────────────────────────

    /**
     * Kicks off the Wi-Fi bring-up exactly once per cycle. The server starts its listener and
     * announces it; the client asks the server to do so. Re-entrant calls (a duplicate
     * WIFI_CONNECT_REQ, or a second large payload) are ignored while one bring-up is in flight.
     */
    private void triggerWifiConnect() {
        synchronized (wifiLock) {
            if (disposed || wifiUp || wifiActivating) return;
            wifiActivating = true;
        }

        if (isServer) {
            startWifiServerAndAnnounce();
        } else {
            sendOverBluetooth(newMessage(SessionControlMessage.TYPE_WIFI_CONNECT_REQ));
        }
    }

    private void startWifiServerAndAnnounce() {
        try {
            // Server-mode connect starts the TCP listener. The client retries its dial, so it
            // tolerates the listener still coming up when READY is sent.
            wifi.connect(null);

            SessionControlMessage ready = newMessage(SessionControlMessage.TYPE_WIFI_CONNECT_READY);
            ready.setSessionToken(ConnectionContext.getInstance().getSessionToken());
            String host = NetworkUtils.getLocalWifiIpAddress();
            ready.setWifiHost(host != null ? host : "127.0.0.1");
            ready.setWifiPort(CoreConfig.DEFAULT_PORT);
            sendOverBluetooth(ready);
        } catch (Exception e) {
            resetWifiActivation();
        }
    }

    private void handleWifiConnectReady(SessionControlMessage message) {
        try {
            ConnectionContext.getInstance().setSessionToken(message.getSessionToken());
            int connectTimeoutSeconds = Math.max(1, CoreConfig.BT_CONNECT_TIMEOUT_MS / 1000);
            wifi.connect(message.getWifiHost(), connectTimeoutSeconds).get();

            SessionControlMessage join = newMessage(SessionControlMessage.TYPE_SESSION_JOIN);
            join.setSessionToken(message.getSessionToken());
            sendOverWifi(join);
        } catch (Exception e) {
            resetWifiActivation();
        }
    }

    private void handleSessionJoin(SessionControlMessage message) {
        String expected = ConnectionContext.getInstance().getSessionToken();
        if (expected == null || !expected.equals(message.getSessionToken())) {
            // Token mismatch — drop the Wi-Fi socket without acknowledging. Bluetooth stays up.
            wifi.disconnect();
            resetWifiActivation();
            return;
        }
        try {
            sendOverWifi(newMessage(SessionControlMessage.TYPE_SESSION_JOIN_ACK)).get();
        } catch (Exception ignored) {
            // Best-effort ACK; the client retries the whole flow if it never arrives.
        }
        markWifiReady();
    }

    private void markWifiReady() {
        synchronized (wifiLock) {
            wifiUp = true;
            wifiActivating = false;
            wifiReady.complete(null);
        }
        startIdleTimer();
    }

    private void resetWifiActivation() {
        synchronized (wifiLock) {
            wifiActivating = false;
        }
    }

    // ── Idle teardown ─────────────────────────────────────────────────

    private void startIdleTimer() {
        synchronized (wifiLock) {
            if (idleTimer != null) return;
            idleTimer = Executors.newSingleThreadScheduledExecutor(r -> {
                Thread t = new Thread(r, "TauSync-WifiIdle");
                t.setDaemon(true);
                return t;
            });
            idleTimer.scheduleAtFixedRate(this::checkWifiIdle,
                    IDLE_CHECK_PERIOD_MS, IDLE_CHECK_PERIOD_MS, TimeUnit.MILLISECONDS);
        }
    }

    private void checkWifiIdle() {
        if (disposed || !wifiUp) return;
        long idleMs = System.currentTimeMillis() - wifi.getLastActivityMillis();
        if (idleMs >= CoreConfig.WIFI_IDLE_TIMEOUT_MS) {
            disconnectWifiForIdle();
        }
    }

    /**
     * Tears down the idle Wi-Fi link intentionally. Because it is intentional the transport does not
     * auto-reconnect, and because Bluetooth is still up the ref-counted
     * {@link ConnectionContext#notifyTransportDisconnected()} does not abort any channels — they
     * simply continue over Bluetooth until the next large payload re-runs the bring-up.
     */
    private void disconnectWifiForIdle() {
        synchronized (wifiLock) {
            if (!wifiUp) return;
            wifiUp = false;
            wifiActivating = false;
            // Fresh incomplete gate so the next large send waits for a new bring-up.
            wifiReady = new CompletableFuture<>();
        }
        try { wifi.disconnect(); } catch (Exception ignored) {}
    }

    // ── Frame helpers ─────────────────────────────────────────────────

    private SessionControlMessage newMessage(String type) {
        SessionControlMessage message = new SessionControlMessage();
        message.setType(type);
        message.setMagicBytes(CoreConfig.MAGIC_BYTES);
        return message;
    }

    private CompletableFuture<Void> sendOverBluetooth(SessionControlMessage message) {
        return bluetooth.sendRaw(buildControlFrame(message));
    }

    private CompletableFuture<Void> sendOverWifi(SessionControlMessage message) {
        return wifi.sendRaw(buildControlFrame(message));
    }

    private byte[] buildControlFrame(SessionControlMessage message) {
        byte[] body = gson.toJson(message).getBytes(StandardCharsets.UTF_8);
        return protocolHandler.buildFrame(CoreConfig.CONTROL_CHANNEL_ID, body, CoreConfig.FLAG_CONTROL);
    }
}

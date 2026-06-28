package com.example.tausync_lib.implementations.transport;

import com.example.tausync_lib.core.CoreConfig;
import com.example.tausync_lib.implementations.management.ConnectionContext;
import com.example.tausync_lib.implementations.protocol.ProtocolHandler;
import com.example.tausync_lib.interfaces.IProtocolHandler;
import com.example.tausync_lib.interfaces.ITransport;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * TCP socket transport. Protocol-agnostic: reads frames via {@link IProtocolHandler} only.
 *
 * <p>Server mode ({@code connect(null)}/{@code connect("")}): binds to
 * {@code 0.0.0.0:DefaultPort}, accepts one client, then stops listening.
 * Client mode: retries every {@link CoreConfig#CLIENT_CONNECT_RETRY_DELAY_SECONDS}
 * until success or disposal.
 *
 * <p>Matches C# SocketTransport.
 */
public class SocketTransport implements ITransport {

    private Socket socket;
    private ServerSocket serverSocket;
    private InputStream inputStream;
    private OutputStream outputStream;
    private volatile boolean connected;
    private volatile boolean disposed;
    private volatile boolean serverMode;
    private Thread receiveThread;
    private Thread acceptThread;
    private Thread reconnectThread;
    private final Semaphore sendLock = new Semaphore(1);
    private final IProtocolHandler protocolHandler;
    private OnDataReceivedListener dataReceivedListener;

    /** True only while an explicit {@link #disconnect()} is tearing the transport down — distinguishes a deliberate close (ends the session) from an unexpected drop (triggers reconnect). */
    private volatile boolean intentionalClose;

    /** True once this transport has been counted in {@link ConnectionContext}, so the matching disconnect decrements exactly once. */
    private volatile boolean counted;

    /** Peer host saved on connect so the reconnect loop (client mode) can re-dial it. */
    private volatile String lastTargetId;

    /**
     * Completed while a live connection exists; replaced with an incomplete future during a
     * reconnect so a send issued mid-drop waits for the link to come back instead of failing.
     * {@link #sendRaw(byte[])} waits on this before writing.
     */
    private volatile CompletableFuture<Void> sendGate = new CompletableFuture<>();

    /**
     * Epoch millis of the last frame sent or received. The hybrid coordinator reads this to decide
     * when the Wi-Fi link has been idle long enough to disconnect. Initialised to "now" so a freshly
     * connected link is not immediately considered idle.
     */
    private volatile long lastActivityMillis = System.currentTimeMillis();

    private int port = CoreConfig.DEFAULT_PORT;

    public SocketTransport() {
        this(null);
    }

    /**
     * @param protocolHandler framing handler; defaults to {@link ProtocolHandler}
     */
    public SocketTransport(IProtocolHandler protocolHandler) {
        this.protocolHandler = protocolHandler != null ? protocolHandler : new ProtocolHandler();
    }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }

    @Override
    public boolean isServerMode() {
        return serverMode;
    }

    /** Epoch millis of the last send or receive on this transport (see {@link #lastActivityMillis}). */
    public long getLastActivityMillis() {
        return lastActivityMillis;
    }

    /**
     * @return true once {@link #close()} has permanently disposed this transport. A disposed
     * transport rejects every {@link #connect(String, Integer)} with "Transport disposed"; only
     * {@link #disconnect()} leaves it reusable. Exposed so the hybrid teardown can be asserted in tests.
     */
    public boolean isDisposed() {
        return disposed;
    }

    @Override
    public TransportKind getTransportType() {
        return TransportKind.WIFI;
    }

    @Override
    public CompletableFuture<Void> connect(String targetId) {
        return connect(targetId, null);
    }

    @Override
    public CompletableFuture<Void> connect(String targetId, Integer timeoutSeconds) {
        if (disposed) {
            return CompletableFuture.failedFuture(new IllegalStateException("Transport disposed"));
        }
        if (connected) {
            disconnect();
        }

        // Re-arm for a fresh session: a prior disconnect() left intentionalClose set, and the
        // gate must start incomplete until this connection succeeds.
        intentionalClose = false;
        sendGate = new CompletableFuture<>();

        boolean wantServer = targetId == null || targetId.trim().isEmpty();
        serverMode = wantServer;

        if (wantServer) {
            return startListening(timeoutSeconds);
        }
        lastTargetId = targetId.trim();
        return connectToServerWithRetry(lastTargetId, timeoutSeconds);
    }

    // ── Server Mode ───────────────────────────────────────────────────

    private CompletableFuture<Void> startListening(Integer timeoutSeconds) {
        CompletableFuture<Void> connectionFuture = new CompletableFuture<>();

        acceptThread = new Thread(() -> {
            try {
                serverSocket = new ServerSocket(port);
                if (timeoutSeconds != null) {
                    // accept() throws SocketTimeoutException when no client arrives in time,
                    // mirroring the C# server-mode _timeoutCts behaviour.
                    serverSocket.setSoTimeout(timeoutSeconds * 1000);
                }
                socket = serverSocket.accept();
                inputStream = socket.getInputStream();
                outputStream = socket.getOutputStream();
                connected = true;
                startReceiveLoop();
                markInitialConnection();
                connectionFuture.complete(null);
            } catch (java.net.SocketTimeoutException e) {
                connectionFuture.completeExceptionally(
                        new java.util.concurrent.TimeoutException(
                                "No client connected within the timeout period."));
            } catch (Exception e) {
                if (!disposed) {
                    connectionFuture.completeExceptionally(e);
                }
            } finally {
                closeServerSocket();
            }
        }, "TauSync-Accept");
        acceptThread.setDaemon(true);
        acceptThread.start();

        return connectionFuture;
    }

    // ── Client Mode ───────────────────────────────────────────────────

    private CompletableFuture<Void> connectToServerWithRetry(String host, Integer timeoutSeconds) {
        CompletableFuture<Void> connectionFuture = new CompletableFuture<>();
        int delayMs = CoreConfig.CLIENT_CONNECT_RETRY_DELAY_SECONDS * 1000;
        // Overall deadline for the whole retry loop; null = retry forever (legacy behaviour).
        final Long deadlineNanos = timeoutSeconds != null
                ? System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(timeoutSeconds)
                : null;

        Thread retryThread = new Thread(() -> {
            while (!connectionFuture.isDone() && !disposed) {
                if (deadlineNanos != null && System.nanoTime() >= deadlineNanos) {
                    connectionFuture.completeExceptionally(
                            new java.util.concurrent.TimeoutException(
                                    "Failed to connect within the timeout period."));
                    return;
                }
                try {
                    Socket attempt = new Socket();
                    // Bound each TCP connect attempt by the remaining budget so a single
                    // attempt to a black-holed IP cannot overrun the caller's timeout.
                    int attemptTimeoutMs = remainingMillis(deadlineNanos);
                    attempt.connect(new java.net.InetSocketAddress(host, port), attemptTimeoutMs);
                    if (connectionFuture.isDone() || disposed) {
                        attempt.close();
                        return;
                    }

                    socket = attempt;
                    inputStream = socket.getInputStream();
                    outputStream = socket.getOutputStream();
                    connected = true;
                    startReceiveLoop();
                    markInitialConnection();
                    connectionFuture.complete(null);
                    return;
                } catch (IOException e) {
                    if (disposed) {
                        connectionFuture.completeExceptionally(
                                new IllegalStateException("Transport disposed during connect"));
                        return;
                    }
                    if (deadlineNanos != null && System.nanoTime() >= deadlineNanos) {
                        connectionFuture.completeExceptionally(
                                new java.util.concurrent.TimeoutException(
                                        "Failed to connect within the timeout period."));
                        return;
                    }
                    try {
                        Thread.sleep(delayMs);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        connectionFuture.completeExceptionally(ie);
                        return;
                    }
                } catch (Exception e) {
                    connectionFuture.completeExceptionally(e);
                    return;
                }
            }
        }, "TauSync-ConnectRetry");
        retryThread.setDaemon(true);
        retryThread.start();

        return connectionFuture;
    }

    /**
     * Milliseconds remaining until the deadline, clamped to int.
     *
     * @param deadlineNanos absolute deadline from {@link System#nanoTime()}, or null for no limit
     * @return remaining millis (>= 1), or 0 meaning "no timeout" when deadline is null
     */
    private static int remainingMillis(Long deadlineNanos) {
        if (deadlineNanos == null) return 0; // Socket.connect(addr, 0) = infinite timeout
        long ms = java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(deadlineNanos - System.nanoTime());
        if (ms <= 0) return 1; // already past deadline; fail fast on the next attempt
        return ms > Integer.MAX_VALUE ? Integer.MAX_VALUE : (int) ms;
    }

    // ── Send ──────────────────────────────────────────────────────────

    @Override
    public CompletableFuture<Void> sendRaw(byte[] data) {
        if (data == null) {
            return CompletableFuture.failedFuture(new IllegalArgumentException("data must not be null"));
        }
        if (disposed) {
            return CompletableFuture.failedFuture(new IllegalStateException("Transport disposed"));
        }

        try {
            // Block briefly if an unexpected drop is being healed, so a write issued during
            // the reconnect window resumes on the new link instead of failing.
            waitForConnection();
        } catch (Exception e) {
            return CompletableFuture.failedFuture(e);
        }
        if (!connected || outputStream == null) {
            return CompletableFuture.failedFuture(new IllegalStateException("Not connected"));
        }

        try {
            sendLock.acquire();
            try {
                outputStream.write(data);
                outputStream.flush();
                lastActivityMillis = System.currentTimeMillis();
            } finally {
                sendLock.release();
            }
            return CompletableFuture.completedFuture(null);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(new RuntimeException("Send interrupted", e));
        } catch (IOException e) {
            return CompletableFuture.failedFuture(new RuntimeException("Send failed", e));
        }
    }

    /**
     * Blocks until the send gate opens (connection live) or the wait budget elapses.
     * Returns immediately during normal operation; only parks during a reconnect window.
     */
    private void waitForConnection() throws Exception {
        CompletableFuture<Void> gate = sendGate;
        if (gate.isDone()) return;
        try {
            gate.get(CoreConfig.SEND_RECONNECT_WAIT_MS, java.util.concurrent.TimeUnit.MILLISECONDS);
        } catch (java.util.concurrent.ExecutionException e) {
            Throwable cause = e.getCause();
            throw cause instanceof Exception ? (Exception) cause : e;
        }
    }

    @Override
    public boolean isConnected() {
        return connected && !disposed && socket != null && !socket.isClosed();
    }

    @Override
    public void setOnDataReceivedListener(OnDataReceivedListener listener) {
        this.dataReceivedListener = listener;
    }

    // ── Receive Loop ──────────────────────────────────────────────────

    private void startReceiveLoop() {
        receiveThread = new Thread(() -> receiveLoop(), "TauSync-Receive");
        receiveThread.setDaemon(true);
        receiveThread.start();
    }

    private void receiveLoop() {
        int headerSize = protocolHandler.getHeaderSize();
        byte[] headerBuffer = new byte[headerSize];

        while (connected && !disposed && inputStream != null) {
            try {
                int headerRead = readExactly(inputStream, headerBuffer, 0, headerSize);
                if (headerRead != headerSize) break;

                int payloadLength = protocolHandler.getPayloadLength(headerBuffer);
                if (payloadLength < 0 || payloadLength > CoreConfig.MAX_PAYLOAD_SIZE) break;

                int totalFrameSize = headerSize + payloadLength;
                byte[] frame = new byte[totalFrameSize];
                System.arraycopy(headerBuffer, 0, frame, 0, headerSize);

                if (payloadLength > 0) {
                    int payloadRead = readExactly(inputStream, frame, headerSize, payloadLength);
                    if (payloadRead != payloadLength) break;
                }

                lastActivityMillis = System.currentTimeMillis();
                IProtocolHandler.ParseResult result = protocolHandler.parseFrame(frame);
                dispatchFrame(result.getTargetId(), result.getPayload(), result.getFlags(), frame);

            } catch (Exception e) {
                break;
            }
        }

        handleConnectionDropped();
    }

    private void dispatchFrame(int targetId, byte[] payload, byte flags, byte[] rawFrame) {
        if (protocolHandler.isControlFrame(targetId, flags)) {
            boolean handled = ConnectionContext.getInstance().dispatch(targetId, payload, flags);
            if (!handled && dataReceivedListener != null) {
                dataReceivedListener.onDataReceived(rawFrame);
            }
            return;
        }
        ConnectionContext.getInstance().dispatch(targetId, payload, flags);
    }

    /**
     * Reads exactly {@code count} bytes from the stream, looping until done or EOF.
     *
     * @return number of bytes actually read (less than count only on EOF)
     */
    private static int readExactly(InputStream stream, byte[] buffer, int offset, int count)
            throws IOException {
        int totalRead = 0;
        while (totalRead < count) {
            int r = stream.read(buffer, offset + totalRead, count - totalRead);
            if (r < 0) return totalRead;
            totalRead += r;
        }
        return totalRead;
    }

    // ── Lifecycle ─────────────────────────────────────────────────────

    /**
     * Marks this transport connected exactly once and counts it in {@link ConnectionContext}.
     * Called only on the FIRST successful connect — reconnects after a drop reuse the same
     * count, so the session is never double-counted.
     */
    private void markInitialConnection() {
        if (!counted) {
            counted = true;
            ConnectionContext.getInstance().notifyTransportConnected();
        }
        sendGate.complete(null);
    }

    /**
     * Explicit, app-initiated teardown. Ends the session for this transport: stops any
     * reconnect attempt and notifies {@link ConnectionContext}, which aborts the open channels
     * and resets state only if this was the last live transport.
     */
    public void disconnect() {
        if (intentionalClose) return;
        intentionalClose = true;
        connected = false;

        // Stop any in-flight reconnect and release a sender parked on the gate.
        Thread rc = reconnectThread;
        if (rc != null) rc.interrupt();
        sendGate.complete(null);

        closeQuietly(inputStream);
        closeQuietly(outputStream);
        closeQuietly(socket);
        closeServerSocket(); // unblocks a reconnect accept(), if one is in progress

        // Decrement the transport count exactly once. Channels are aborted (synthetic FIN so
        // blocked read() calls return EOF) and state reset only when the count hits zero.
        if (counted) {
            counted = false;
            ConnectionContext.getInstance().notifyTransportDisconnected();
        }

        Thread rt = receiveThread;
        if (rt != null && rt != Thread.currentThread()) {
            rt.interrupt();
            try { rt.join(2000); } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        }

        inputStream = null;
        outputStream = null;
        socket = null;
    }

    /**
     * Handles the receive loop exiting on a broken link. An explicit disconnect ends the
     * session; an unexpected drop instead tears down only the dead socket — keeping the
     * channels, handlers, and transport count intact — and starts reconnecting so the session
     * resumes transparently.
     */
    private void handleConnectionDropped() {
        if (intentionalClose || disposed) return;
        if (!connected) return;
        connected = false;

        // Fresh incomplete gate so sends block until the link is back.
        sendGate = new CompletableFuture<>();

        closeQuietly(inputStream);
        closeQuietly(outputStream);
        closeQuietly(socket);
        inputStream = null;
        outputStream = null;
        socket = null;

        startReconnectLoop();
    }

    private void startReconnectLoop() {
        reconnectThread = new Thread(this::reconnectLoop, "TauSync-Reconnect");
        reconnectThread.setDaemon(true);
        reconnectThread.start();
    }

    /**
     * Retries the connection with exponential back-off until it succeeds or an explicit
     * disconnect stops it. On success it restarts the receive loop and opens the send gate,
     * all on the same channel handlers — the layers above never see the gap.
     */
    private void reconnectLoop() {
        int delayMs = CoreConfig.RECONNECT_INITIAL_DELAY_MS;
        while (!disposed && !intentionalClose) {
            try {
                boolean reconnected = serverMode ? tryReListen() : tryReconnectClient();
                if (reconnected) {
                    connected = true;
                    startReceiveLoop();
                    sendGate.complete(null);
                    return;
                }
            } catch (Exception ignored) {
                // transient failure — fall through to back-off and retry
            }
            try {
                Thread.sleep(delayMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            delayMs = Math.min(delayMs * 2, CoreConfig.RECONNECT_MAX_DELAY_MS);
        }
    }

    private boolean tryReconnectClient() {
        try {
            Socket attempt = new Socket();
            attempt.connect(new java.net.InetSocketAddress(lastTargetId, port),
                    CoreConfig.RECONNECT_MAX_DELAY_MS);
            socket = attempt;
            inputStream = socket.getInputStream();
            outputStream = socket.getOutputStream();
            return true;
        } catch (IOException e) {
            return false;
        }
    }

    private boolean tryReListen() {
        try {
            serverSocket = new ServerSocket(port);
            socket = serverSocket.accept();
            inputStream = socket.getInputStream();
            outputStream = socket.getOutputStream();
            return true;
        } catch (IOException e) {
            return false;
        } finally {
            closeServerSocket();
        }
    }

    @Override
    public void close() {
        if (disposed) return;
        disposed = true;
        disconnect();
        closeServerSocket();

        Thread at = acceptThread;
        if (at != null && at != Thread.currentThread()) {
            at.interrupt();
            try { at.join(2000); } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private void closeServerSocket() {
        if (serverSocket != null) {
            try { serverSocket.close(); } catch (IOException ignored) {}
            serverSocket = null;
        }
    }

    private static void closeQuietly(AutoCloseable closeable) {
        if (closeable == null) return;
        try { closeable.close(); } catch (Exception ignored) {}
    }

    @SuppressWarnings("unused")
    private static void closeQuietly(Socket socket) {
        if (socket == null) return;
        try { socket.close(); } catch (Exception ignored) {}
    }
}

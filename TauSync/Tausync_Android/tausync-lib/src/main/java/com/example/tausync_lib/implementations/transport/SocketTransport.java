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
    private final Semaphore sendLock = new Semaphore(1);
    private final IProtocolHandler protocolHandler;
    private OnDataReceivedListener dataReceivedListener;

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

        boolean wantServer = targetId == null || targetId.trim().isEmpty();
        serverMode = wantServer;

        if (wantServer) {
            return startListening(timeoutSeconds);
        }
        return connectToServerWithRetry(targetId.trim(), timeoutSeconds);
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
        if (!connected || outputStream == null) {
            return CompletableFuture.failedFuture(new IllegalStateException("Not connected"));
        }

        try {
            sendLock.acquire();
            try {
                outputStream.write(data);
                outputStream.flush();
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

                IProtocolHandler.ParseResult result = protocolHandler.parseFrame(frame);
                dispatchFrame(result.getTargetId(), result.getPayload(), result.getFlags(), frame);

            } catch (Exception e) {
                break;
            }
        }

        if (connected) {
            disconnect();
        }
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

    public void disconnect() {
        if (!connected) return;
        connected = false;

        closeQuietly(inputStream);
        closeQuietly(outputStream);
        closeQuietly(socket);

        // Unblock every reader stuck on an open channel stream. The peer is gone, so no
        // FIN will ever arrive — deliver a synthetic FIN to each handler so blocked
        // read() calls return EOF instead of hanging forever.
        ConnectionContext.getInstance().abortAllChannels();

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

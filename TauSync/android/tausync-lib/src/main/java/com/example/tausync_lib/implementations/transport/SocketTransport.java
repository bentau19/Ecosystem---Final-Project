package com.tausync.implementations.transport;

import com.tausync.core.CoreConfig;
import com.tausync.interfaces.ITransport;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * TCP socket transport. Per spec: sends/receives raw TPack (8-byte header + payload).
 * Performs TPack reassembly: buffers incoming bytes until a complete TPack is available,
 * then invokes OnDataReceived with the full packet. Connect(null/empty) = server mode (listen and wait for one client).
 * Matches C# SocketTransport.
 */
public class SocketTransport implements ITransport {

    public static final int DEFAULT_PORT = CoreConfig.DEFAULT_PORT;

    private Socket socket;
    private ServerSocket serverSocket;
    private InputStream inputStream;
    private OutputStream outputStream;
    private final AtomicBoolean connected = new AtomicBoolean(false);
    private final AtomicBoolean disposed = new AtomicBoolean(false);
    private volatile Future<?> receiveTask;
    private volatile CompletableFuture<Void> connectionFuture; // for server mode
    private final ExecutorService executor = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r);
        t.setDaemon(true);
        return t;
    });
    private final byte[] headerBuffer = new byte[CoreConfig.TPACK_HEADER_SIZE];
    private byte[] receiveBuffer;
    private OnDataReceivedListener dataReceivedListener;
    private int port = DEFAULT_PORT;

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    @Override
    public void setOnDataReceivedListener(OnDataReceivedListener listener) {
        this.dataReceivedListener = listener;
    }

    @Override
    public CompletableFuture<Void> connect(String targetId) {
        if (disposed.get()) {
            return CompletableFuture.failedFuture(new IllegalStateException("Transport is disposed"));
        }
        disconnect();

        if (targetId == null || targetId.trim().isEmpty()) {
            return startListeningAndWait();
        }

        CompletableFuture<Void> future = new CompletableFuture<>();
        executor.execute(() -> {
            try {
                socket = new Socket(targetId, port);
                inputStream = socket.getInputStream();
                outputStream = socket.getOutputStream();
                connected.set(true);
                startReceiveLoop();
                future.complete(null);
            } catch (IOException e) {
                future.completeExceptionally(e);
            }
        });
        return future;
    }

    private CompletableFuture<Void> startListeningAndWait() {
        connectionFuture = new CompletableFuture<>();
        executor.execute(() -> {
            try {
                serverSocket = new ServerSocket(port);
                Socket client = serverSocket.accept();
                socket = client;
                inputStream = socket.getInputStream();
                outputStream = socket.getOutputStream();
                connected.set(true);
                startReceiveLoop();
                if (connectionFuture != null) {
                    connectionFuture.complete(null);
                }
            } catch (IOException e) {
                if (connectionFuture != null) {
                    connectionFuture.completeExceptionally(e);
                }
            }
        });
        return connectionFuture;
    }

    @Override
    public CompletableFuture<Void> sendRaw(byte[] data) {
        if (data == null) {
            return CompletableFuture.failedFuture(new IllegalArgumentException("data cannot be null"));
        }
        if (!connected.get() || outputStream == null) {
            return CompletableFuture.failedFuture(new IllegalStateException("Not connected"));
        }
        return CompletableFuture.runAsync(() -> {
            synchronized (outputStream) {
                try {
                    outputStream.write(data);
                    outputStream.flush();
                } catch (IOException e) {
                    throw new RuntimeException(e);
                }
            }
        }, executor);
    }

    @Override
    public boolean isConnected() {
        return connected.get() && !disposed.get() && socket != null && socket.isConnected() && !socket.isClosed();
    }

    private void disconnect() {
        if (!connected.get()) return;
        connected.set(false);
        if (receiveTask != null) {
            receiveTask.cancel(true);
        }
        try {
            if (inputStream != null) inputStream.close();
            if (outputStream != null) outputStream.close();
            if (socket != null) socket.close();
        } catch (IOException ignored) {
        }
        inputStream = null;
        outputStream = null;
        socket = null;
    }

    private void startReceiveLoop() {
        receiveTask = executor.submit(this::receiveLoop);
    }

    private void receiveLoop() {
        while (connected.get() && inputStream != null && !disposed.get()) {
            try {
                int headerRead = readExactly(inputStream, headerBuffer, 0, CoreConfig.TPACK_HEADER_SIZE);
                if (headerRead != CoreConfig.TPACK_HEADER_SIZE) break;

                int payloadLength = (headerBuffer[0] & 0xFF) | ((headerBuffer[1] & 0xFF) << 8)
                        | ((headerBuffer[2] & 0xFF) << 16) | ((headerBuffer[3] & 0xFF) << 24);
                if (payloadLength < 0) break;

                int totalSize = CoreConfig.TPACK_HEADER_SIZE + payloadLength;
                if (receiveBuffer == null || receiveBuffer.length < totalSize) {
                    receiveBuffer = new byte[Math.max(totalSize, 65536)];
                }
                System.arraycopy(headerBuffer, 0, receiveBuffer, 0, CoreConfig.TPACK_HEADER_SIZE);
                if (payloadLength > 0) {
                    int payloadRead = readExactly(inputStream, receiveBuffer, CoreConfig.TPACK_HEADER_SIZE, payloadLength);
                    if (payloadRead != payloadLength) break;
                }

                byte[] packet = new byte[totalSize];
                System.arraycopy(receiveBuffer, 0, packet, 0, totalSize);
                if (dataReceivedListener != null) {
                    dataReceivedListener.onDataReceived(packet);
                }
            } catch (Exception e) {
                break;
            }
        }
        if (connected.get()) {
            disconnect();
        }
    }

    private static int readExactly(InputStream in, byte[] buf, int offset, int count) throws IOException {
        int total = 0;
        while (total < count) {
            int r = in.read(buf, offset + total, count - total);
            if (r <= 0) return total;
            total += r;
        }
        return total;
    }

    @Override
    public void close() {
        if (disposed.getAndSet(true)) return;
        disconnect();
        try {
            if (serverSocket != null) serverSocket.close();
        } catch (IOException ignored) {
        }
        serverSocket = null;
        executor.shutdown();
    }
}

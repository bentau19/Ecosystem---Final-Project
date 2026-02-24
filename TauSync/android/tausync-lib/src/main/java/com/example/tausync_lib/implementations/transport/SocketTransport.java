package com.tausync.implementations.transport;

import com.tausync.interfaces.ITransport;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Simple TCP Socket transport implementation.
 */
public class SocketTransport implements ITransport {
    public static final int DEFAULT_PORT = 8888;

    private Socket socket;
    private DataInputStream inputStream;
    private DataOutputStream outputStream;
    private String targetId;
    private AtomicBoolean isConnected = new AtomicBoolean(false);
    private ExecutorService executorService;
    private Future<?> receiveTask;
    private DataReceivedListener dataReceivedListener;
    private int port = DEFAULT_PORT;

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    @Override
    public void connect(String targetId) {
        if (targetId == null || targetId.trim().isEmpty()) {
            throw new IllegalArgumentException("Target ID cannot be null or empty.");
        }

        if (isConnected.get()) {
            disconnect();
        }

        try {
            this.targetId = targetId;
            socket = new Socket(targetId, port);
            inputStream = new DataInputStream(socket.getInputStream());
            outputStream = new DataOutputStream(socket.getOutputStream());
            isConnected.set(true);

            // Start receiving data in background
            executorService = Executors.newSingleThreadExecutor();
            receiveTask = executorService.submit(this::receiveLoop);
        } catch (IOException ex) {
            isConnected.set(false);
            throw new IllegalStateException("Failed to connect to " + targetId + ":" + port, ex);
        }
    }

    @Override
    public void sendRaw(byte[] data) {
        if (data == null) {
            throw new IllegalArgumentException("Data cannot be null.");
        }

        if (!isConnected.get() || outputStream == null) {
            throw new IllegalStateException("Not connected. Call connect() first.");
        }

        try {
            synchronized (outputStream) {
                // Send data length first (4 bytes)
                outputStream.writeInt(data.length);
                // Send actual data
                outputStream.write(data);
                outputStream.flush();
            }
        } catch (IOException ex) {
            throw new IllegalStateException("Failed to send data via socket.", ex);
        }
    }

    @Override
    public boolean isConnected() {
        return isConnected.get() && socket != null && socket.isConnected() && !socket.isClosed();
    }

    public void disconnect() {
        if (isConnected.get()) {
            isConnected.set(false);

            if (receiveTask != null) {
                receiveTask.cancel(true);
            }

            try {
                if (inputStream != null) {
                    inputStream.close();
                }
                if (outputStream != null) {
                    outputStream.close();
                }
                if (socket != null) {
                    socket.close();
                }
            } catch (IOException ex) {
                // Ignore errors during cleanup
            }

            if (executorService != null) {
                executorService.shutdown();
            }

            inputStream = null;
            outputStream = null;
            socket = null;
            targetId = null;
        }
    }

    @Override
    public void setDataReceivedListener(DataReceivedListener listener) {
        this.dataReceivedListener = listener;
    }

    private void receiveLoop() {
        while (isConnected.get() && inputStream != null) {
            try {
                // Read data length (4 bytes)
                int dataLength = inputStream.readInt();
                if (dataLength < 0 || dataLength > 10 * 1024 * 1024) { // Max 10MB
                    throw new IllegalStateException("Invalid data length: " + dataLength);
                }

                // Read actual data
                byte[] data = new byte[dataLength];
                int totalRead = 0;
                while (totalRead < dataLength) {
                    int read = inputStream.read(data, totalRead, dataLength - totalRead);
                    if (read == -1) {
                        break;
                    }
                    totalRead += read;
                }

                if (totalRead == dataLength && dataReceivedListener != null) {
                    dataReceivedListener.onDataReceived(data);
                }
            } catch (IOException ex) {
                break;
            }
        }

        if (isConnected.get()) {
            disconnect();
        }
    }
}

package com.tausync.implementations.transport;

import com.tausync.interfaces.ITransport;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReentrantLock;

/**
 * Professional TCP Socket transport implementation with request-response support and streaming.
 * Protocol: [4-byte Length (Big-Endian)][16-byte CorrelationID][Payload]
 */
public class SocketTransport implements ITransport {
    public static final int DEFAULT_PORT = 8888;
    private static final int STREAMING_THRESHOLD = 1024 * 1024; // 1MB
    private static final int CHUNK_BUFFER_SIZE = 64 * 1024; // 64KB
    private static final int CORRELATION_ID_LENGTH = 16; // 16 bytes

    private Socket socket;
    private DataInputStream inputStream;
    private DataOutputStream outputStream;
    private String targetId;
    private AtomicBoolean isConnected = new AtomicBoolean(false);
    private ExecutorService executorService;
    private Future<?> receiveTask;
    private ITransport.DataReceivedListener dataReceivedListener;
    private ITransport.DataReceivedWithCorrelationListener dataReceivedWithCorrelationListener;
    private ITransport.StreamChunkReceivedListener streamChunkReceivedListener;
    private int port = DEFAULT_PORT;

    // Thread safety for sending
    private final ReentrantLock sendLock = new ReentrantLock();

    // Request-response tracking
    private final ConcurrentHashMap<String, CompletableFuture<byte[]>> pendingRequests = new ConcurrentHashMap<>();

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    /**
     * Sets the listener for small messages (< 1MB)
     */
    @Override
    public void setDataReceivedListener(ITransport.DataReceivedListener listener) {
        this.dataReceivedListener = listener;
    }

    /**
     * Sets the listener for small messages with correlation ID (< 1MB)
     * Use this when you need the correlationId to send responses.
     */
    @Override
    public void setDataReceivedWithCorrelationListener(ITransport.DataReceivedWithCorrelationListener listener) {
        this.dataReceivedWithCorrelationListener = listener;
    }

    /**
     * Sets the listener for streaming chunks (>= 1MB)
     */
    @Override
    public void setStreamChunkReceivedListener(ITransport.StreamChunkReceivedListener listener) {
        this.streamChunkReceivedListener = listener;
    }

    /**
     * Sends a request and waits for a response with the specified correlationId.
     *
     * @param data          The data to send (will be prefixed with correlationId)
     * @param correlationId Unique identifier for request-response matching (max 16 bytes)
     * @param timeoutMs     Timeout in milliseconds
     * @return CompletableFuture that completes with the response data (without correlationId header)
     */
    public CompletableFuture<byte[]> sendRequest(byte[] data, String correlationId, long timeoutMs) {
        if (data == null) {
            throw new IllegalArgumentException("Data cannot be null.");
        }
        if (correlationId == null || correlationId.trim().isEmpty()) {
            throw new IllegalArgumentException("CorrelationId cannot be null or empty.");
        }
        if (correlationId.length() > CORRELATION_ID_LENGTH) {
            throw new IllegalArgumentException("CorrelationId cannot exceed " + CORRELATION_ID_LENGTH + " bytes.");
        }
        if (!isConnected.get() || outputStream == null) {
            throw new IllegalStateException("Not connected. Call connect() first.");
        }

        // Create CompletableFuture for this request
        CompletableFuture<byte[]> future = new CompletableFuture<>();

        // Add to pending requests
        if (pendingRequests.putIfAbsent(correlationId, future) != null) {
            throw new IllegalStateException("A request with correlationId '" + correlationId + "' is already pending.");
        }

        try {
            // Encode correlationId to bytes
            byte[] correlationBytes = encodeCorrelationId(correlationId);

            // Prepend correlationId to data
            byte[] messageWithHeader = new byte[CORRELATION_ID_LENGTH + data.length];
            System.arraycopy(correlationBytes, 0, messageWithHeader, 0, CORRELATION_ID_LENGTH);
            System.arraycopy(data, 0, messageWithHeader, CORRELATION_ID_LENGTH, data.length);

            // Send the message (thread-safe)
            sendRaw(messageWithHeader);

            // Set timeout
            CompletableFuture<byte[]> timeoutFuture = new CompletableFuture<>();
            Executors.newSingleThreadScheduledExecutor().schedule(() -> {
                if (pendingRequests.remove(correlationId) == future) {
                    future.completeExceptionally(new TimeoutException(
                            "Request with correlationId '" + correlationId + "' timed out after " + timeoutMs + "ms."));
                }
            }, timeoutMs, TimeUnit.MILLISECONDS);

            return future;
        } catch (Exception ex) {
            // Clean up on error
            pendingRequests.remove(correlationId);
            future.completeExceptionally(ex);
            return future;
        }
    }

    /**
     * Encodes a correlation ID string to a 16-byte array (UTF-8, null-padded)
     */
    private byte[] encodeCorrelationId(String correlationId) {
        byte[] bytes = new byte[CORRELATION_ID_LENGTH];
        byte[] idBytes = correlationId.getBytes(StandardCharsets.UTF_8);
        int copyLength = Math.min(idBytes.length, CORRELATION_ID_LENGTH);
        System.arraycopy(idBytes, 0, bytes, 0, copyLength);
        return bytes;
    }

    /**
     * Decodes a 16-byte correlation ID array to a string (UTF-8, null-terminated)
     */
    private String decodeCorrelationId(byte[] header) {
        // Find null terminator or use full length
        int length = 0;
        for (int i = 0; i < CORRELATION_ID_LENGTH; i++) {
            if (header[i] == 0) {
                length = i;
                break;
            }
        }
        if (length == 0) length = CORRELATION_ID_LENGTH;
        return new String(header, 0, length, StandardCharsets.UTF_8);
    }

    /**
     * Checks if correlation ID bytes represent an unsolicited message (all zeros)
     */
    private boolean isUnsolicitedMessage(byte[] correlationIdBytes) {
        for (int i = 0; i < CORRELATION_ID_LENGTH; i++) {
            if (correlationIdBytes[i] != 0) {
                return false;
            }
        }
        return true;
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

        sendLock.lock();
        try {
            // Send data length first (4 bytes, Big-Endian/Network Order)
            outputStream.writeInt(data.length);
            // Send actual data
            outputStream.write(data);
            outputStream.flush();
        } catch (IOException ex) {
            throw new IllegalStateException("Failed to send data via socket.", ex);
        } finally {
            sendLock.unlock();
        }
    }

    @Override
    public boolean isConnected() {
        return isConnected.get() && socket != null && socket.isConnected() && !socket.isClosed();
    }

    public void disconnect() {
        if (isConnected.get()) {
            isConnected.set(false);

            // Cancel all pending requests
            for (CompletableFuture<byte[]> future : pendingRequests.values()) {
                future.completeExceptionally(new IllegalStateException("Connection closed."));
            }
            pendingRequests.clear();

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

    private void receiveLoop() {
        while (isConnected.get() && inputStream != null) {
            try {
                // Read data length (4 bytes, Big-Endian)
                int dataLength = inputStream.readInt();
                if (dataLength < 0 || dataLength > Integer.MAX_VALUE) {
                    throw new IllegalStateException("Invalid data length: " + dataLength);
                }

                // Read correlation ID (16 bytes)
                byte[] correlationIdBytes = new byte[CORRELATION_ID_LENGTH];
                int correlationBytesRead = 0;
                while (correlationBytesRead < CORRELATION_ID_LENGTH) {
                    int read = inputStream.read(correlationIdBytes, correlationBytesRead, 
                            CORRELATION_ID_LENGTH - correlationBytesRead);
                    if (read == -1) {
                        break;
                    }
                    correlationBytesRead += read;
                }

                if (correlationBytesRead != CORRELATION_ID_LENGTH) {
                    break; // Connection closed
                }

                // Calculate payload length (dataLength includes correlationId header)
                int payloadLength = dataLength - CORRELATION_ID_LENGTH;
                if (payloadLength < 0) {
                    throw new IllegalStateException("Invalid payload length: " + payloadLength);
                }

                // Check if this is a response to a pending request
                if (!isUnsolicitedMessage(correlationIdBytes)) {
                    String correlationId = decodeCorrelationId(correlationIdBytes);
                    CompletableFuture<byte[]> future = pendingRequests.remove(correlationId);

                    if (future != null) {
                        // This is a response - read payload and resolve future
                        if (payloadLength > STREAMING_THRESHOLD) {
                            // For large responses, we still need to buffer (can't stream responses easily)
                            // This is a limitation - streaming is mainly for unsolicited messages
                            byte[] payload = readFully(payloadLength);
                            future.complete(payload);
                        } else {
                            byte[] payload = readFully(payloadLength);
                            future.complete(payload);
                        }
                        continue; // Don't trigger general listeners for responses
                    }
                }

                // This is an unsolicited message - handle based on size
                // NOTE: For unsolicited messages, each chunk is sent as a separate packet
                // So we don't use receiveStreaming() - we read each packet individually
                if (payloadLength > STREAMING_THRESHOLD && streamChunkReceivedListener != null) {
                    // Large unsolicited message - read and route to stream handler
                    byte[] payload = readFully(payloadLength);
                    streamChunkReceivedListener.onStreamChunkReceived(payload, true); // Single large chunk, likely final
                } else {
                    // Buffered mode: read entire message
                    byte[] payload = readFully(payloadLength);
                    
                    // Smart routing based on message size:
                    // - Large messages (>= CHUNK_BUFFER_SIZE/2) are likely stream data -> route to stream handler
                    // - Small messages (< CHUNK_BUFFER_SIZE/2) are likely control messages/interrupts -> route to message handler
                    boolean isLikelyStreamData = payload.length >= (CHUNK_BUFFER_SIZE / 2);
                    
                    if (isLikelyStreamData && streamChunkReceivedListener != null) {
                        // Route large unsolicited messages to streaming handler (likely stream chunks)
                        // Check if this is the final chunk: if payload is smaller than full chunk size (minus header),
                        // it's likely the final chunk. Full chunk = 64KB + 16 bytes header = 65552 bytes
                        // But we only check the payload size (without header), so if payload < 64KB, it's likely final
                        boolean isFinal = (payload.length < CHUNK_BUFFER_SIZE);
                        streamChunkReceivedListener.onStreamChunkReceived(payload, isFinal);
                        // CRITICAL: DO NOT invoke message listeners - this is exclusive routing
                    } else {
                        // Small messages or no stream handler registered -> treat as regular message/interrupt
                        // Check if this is JSON (TransferRequest) or plain text (interrupt)
                        boolean isJson = false;
                        if (payload.length < 1024 * 10) { // Small message, might be JSON
                            try {
                                String text = new String(payload, StandardCharsets.UTF_8);
                                if (text.trim().startsWith("{") && text.contains("\"MagicBytes\"")) {
                                    isJson = true;
                                }
                            } catch (Exception e) {
                                // Not valid UTF-8, not JSON
                            }
                        }
                        
                        // If JSON, route to correlation-aware listener (for handshake)
                        // If not JSON, route to regular listener (for interrupts)
                        if (isJson && dataReceivedWithCorrelationListener != null) {
                            String correlationId = isUnsolicitedMessage(correlationIdBytes) 
                                ? null 
                                : decodeCorrelationId(correlationIdBytes);
                            dataReceivedWithCorrelationListener.onDataReceived(payload, correlationId);
                        } else if (dataReceivedListener != null) {
                            // Not JSON or no correlation listener -> treat as interrupt
                            dataReceivedListener.onDataReceived(payload);
                        } else if (dataReceivedWithCorrelationListener != null) {
                            // Fallback: if no regular listener, use correlation listener
                            String correlationId = isUnsolicitedMessage(correlationIdBytes) 
                                ? null 
                                : decodeCorrelationId(correlationIdBytes);
                            dataReceivedWithCorrelationListener.onDataReceived(payload, correlationId);
                        }
                    }
                }
            } catch (IOException ex) {
                break;
            } catch (Exception ex) {
                break;
            }
        }

        if (isConnected.get()) {
            disconnect();
        }
    }

    /**
     * Reads exactly the specified number of bytes from the input stream
     */
    private byte[] readFully(int length) throws IOException {
        byte[] data = new byte[length];
        int totalRead = 0;
        while (totalRead < length) {
            int read = inputStream.read(data, totalRead, length - totalRead);
            if (read == -1) {
                throw new IOException("Unexpected end of stream");
            }
            totalRead += read;
        }
        return data;
    }

    /**
     * Receives data in streaming mode (chunks of 64KB)
     */
    private void receiveStreaming(int payloadLength) {
        byte[] chunkBuffer = new byte[CHUNK_BUFFER_SIZE];
        int remainingBytes = payloadLength;

        try {
            while (remainingBytes > 0 && isConnected.get()) {
                int chunkSize = Math.min(CHUNK_BUFFER_SIZE, remainingBytes);
                int bytesRead = 0;
                while (bytesRead < chunkSize) {
                    int read = inputStream.read(chunkBuffer, bytesRead, chunkSize - bytesRead);
                    if (read == -1) {
                        return; // Connection closed
                    }
                    bytesRead += read;
                }

                remainingBytes -= bytesRead;
                boolean isFinal = (remainingBytes == 0);

                // Create a copy for the listener
                byte[] chunk = new byte[bytesRead];
                System.arraycopy(chunkBuffer, 0, chunk, 0, bytesRead);

                // Notify stream chunk listener
                if (streamChunkReceivedListener != null) {
                    streamChunkReceivedListener.onStreamChunkReceived(chunk, isFinal);
                }
            }
        } catch (IOException ex) {
            // Connection error during streaming
        }
    }

}

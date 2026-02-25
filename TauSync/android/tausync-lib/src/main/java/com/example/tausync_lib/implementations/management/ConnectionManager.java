package com.example.tausync_lib.implementations.management;

import com.google.gson.Gson;
import com.tausync.core.ConnectionStatus;
import com.tausync.implementations.transport.SocketTransport;
import com.tausync.interfaces.IConnectionManager;
import com.tausync.interfaces.ITransport;
import com.tausync.models.TransferRequest;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

/**
 * Connection manager implementation with handshake protocol and streaming support.
 */
public class ConnectionManager implements IConnectionManager {
    private static final long LARGE_FILE_THRESHOLD = 1024 * 1024; // 1MB
    private static final int STREAM_CHUNK_SIZE = 64 * 1024; // 64KB
    private static final int HANDSHAKE_TIMEOUT_SECONDS = 30;

    private SocketTransport transport;
    private Gson gson;
    private IConnectionManager.RequestReceivedListener requestReceivedListener;
    private IConnectionManager.ErrorOccurredListener errorOccurredListener;
    private IConnectionManager.DataChunkListener dataChunkListener;
    
    // Executor for UI callbacks and file I/O
    private ExecutorService callbackExecutor;

    public ConnectionManager() {
        this.gson = new Gson();
        this.callbackExecutor = Executors.newCachedThreadPool();
    }

    /**
     * Initializes the connection manager with transport.
     */
    public void initialize(ITransport transport) {
        if (transport == null) {
            throw new IllegalArgumentException("Transport cannot be null.");
        }

        if (!(transport instanceof SocketTransport)) {
            throw new IllegalArgumentException("Transport must be a SocketTransport instance.");
        }

        this.transport = (SocketTransport) transport;

        // Register message handler for incoming TransferRequests (handshake)
        // Use correlation-aware listener to get correlationId for responses
        this.transport.setDataReceivedWithCorrelationListener(this::onTransportDataReceivedWithCorrelation);

        // Register stream chunk handler for incoming large files
        this.transport.setStreamChunkReceivedListener(this::onTransportStreamChunkReceived);
    }

    /**
     * Sets the listener for data chunks (for writing to file).
     */
    @Override
    public void setDataChunkListener(IConnectionManager.DataChunkListener listener) {
        this.dataChunkListener = listener;
    }

    /**
     * Sends a TransferRequest with streaming data support (async).
     * Implements handshake protocol: sends metadata, waits for OK/REJECT, then streams data.
     */
    @Override
    public CompletableFuture<Void> smartSend(InputStream dataStream, TransferRequest req) {
        if (dataStream == null) {
            throw new IllegalArgumentException("Data stream cannot be null.");
        }
        if (req == null) {
            throw new IllegalArgumentException("Transfer request cannot be null.");
        }
        if (!req.isValid()) {
            throw new IllegalArgumentException("Transfer request is invalid.");
        }
        if (transport == null) {
            throw new IllegalStateException("Connection manager is not initialized. Call initialize() first.");
        }
        if (!transport.isConnected()) {
            throw new IllegalStateException("Transport is not connected.");
        }

        // Generate RequestId if not provided
        if (req.getRequestId() == null || req.getRequestId().trim().isEmpty()) {
            req.setRequestId(UUID.randomUUID().toString().replace("-", "").substring(0, 16));
        }

        return CompletableFuture.runAsync(() -> {
            try {
                // Step 1: Serialize TransferRequest metadata to JSON (without payload)
                byte[] originalPayload = req.getPayload();
                req.setPayload(new byte[0]); // Metadata only, no payload in handshake

                String json = gson.toJson(req);
                byte[] metadataBytes = json.getBytes(StandardCharsets.UTF_8);

                // Step 2: Handshake - Send metadata and wait for response
                CompletableFuture<byte[]> handshakeFuture = transport.sendRequest(
                        metadataBytes,
                        req.getRequestId(),
                        HANDSHAKE_TIMEOUT_SECONDS * 1000L
                );

                byte[] handshakeResponse = handshakeFuture.get();

                // Step 3: Check handshake response
                String responseText = new String(handshakeResponse, StandardCharsets.UTF_8).trim().toUpperCase();
                if (!"OK".equals(responseText)) {
                    if ("REJECT".equals(responseText)) {
                        throw new IllegalStateException("Transfer request was rejected by the remote peer.");
                    }
                    throw new IllegalStateException("Unexpected handshake response: " + responseText);
                }

                // Step 4: Stream data in chunks (memory-efficient)
                streamData(dataStream);

            } catch (Exception ex) {
                notifyErrorOccurred(ex);
                throw new IllegalStateException("Failed to send transfer request.", ex);
            }
        }, callbackExecutor);
    }

    /**
     * Legacy SmartSend for backward compatibility (sends TransferRequest with payload in memory)
     */
    @Override
    public void smartSend(TransferRequest req) {
        if (req == null) {
            throw new IllegalArgumentException("Transfer request cannot be null.");
        }

        // Convert payload to stream and use async version
        try (ByteArrayInputStream stream = new ByteArrayInputStream(req.getPayload() != null ? req.getPayload() : new byte[0])) {
            smartSend(stream, req).join();
        } catch (Exception ex) {
            notifyErrorOccurred(ex);
            throw new IllegalStateException("Failed to send transfer request.", ex);
        }
    }

    /**
     * Streams data from the provided stream in 64KB chunks.
     * Memory-efficient: doesn't load entire stream into RAM.
     * CRITICAL: Each chunk is prefixed with 16-byte zero header (unsolicited message indicator).
     */
    private void streamData(InputStream dataStream) throws IOException {
        byte[] buffer = new byte[STREAM_CHUNK_SIZE];
        // 16-byte zero header for unsolicited stream chunks (protocol requirement)
        byte[] zeroHeader = new byte[16]; // All zeros by default - indicates unsolicited message
        
        // CRITICAL: Reset stream position to start (if supported)
        // Note: For ByteArrayInputStream, markSupported() returns true
        // For FileInputStream, we can't reset, but that's usually fine as streams are read once
        if (dataStream.markSupported()) {
            // Mark the current position (should be at start for new streams)
            dataStream.mark(Integer.MAX_VALUE);
            // Reset to the marked position (start)
            dataStream.reset();
        }

        int bytesRead;
        while ((bytesRead = dataStream.read(buffer)) > 0) {
            // Create packet with exact size: 16 (header) + bytesRead (data)
            byte[] packet = new byte[16 + bytesRead];
            
            // Prepend 16-byte zero header (unsolicited message indicator)
            System.arraycopy(zeroHeader, 0, packet, 0, 16);
            
            // Copy actual data chunk after the header
            System.arraycopy(buffer, 0, packet, 16, bytesRead);
            
            // Send packet (SocketTransport will add 4-byte length prefix automatically)
            // Final format: [4-byte Length][16-byte CorrelationID (zeros)][Payload]
            transport.sendRaw(packet);
        }
    }

    /**
     * Handles incoming messages from transport (handshake requests).
     * Decides whether to accept or reject, then sends response with same correlationId.
     */
    private void onTransportDataReceivedWithCorrelation(byte[] message, String correlationId) {
        callbackExecutor.execute(() -> {
            try {
                // Check if this is JSON (TransferRequest) or plain text (interrupt)
                String json = new String(message, StandardCharsets.UTF_8);
                
                // If not JSON, this is likely an interrupt - don't process as TransferRequest
                if (!json.trim().startsWith("{") || !json.contains("\"MagicBytes\"")) {
                    // This is not a TransferRequest - likely an interrupt message
                    // Don't process it here, let it fall through to dataReceivedListener
                    // But we don't have access to transport's dataReceivedListener from here
                    // So we'll just ignore it (it should be handled by transport's listener)
                    return;
                }
                
                // Deserialize JSON to TransferRequest
                TransferRequest req = gson.fromJson(json, TransferRequest.class);

                if (req == null) {
                    throw new IllegalStateException("Failed to deserialize transfer request.");
                }

                // Use correlationId from transport header if RequestId not in JSON
                if ((req.getRequestId() == null || req.getRequestId().trim().isEmpty()) 
                    && correlationId != null && !correlationId.trim().isEmpty()) {
                    req.setRequestId(correlationId);
                }

                if (!req.isValid()) {
                    if (correlationId != null && !correlationId.trim().isEmpty()) {
                        sendHandshakeResponse(correlationId, "REJECT");
                    }
                    throw new IllegalStateException("Received invalid transfer request.");
                }

                // Decompress if needed (for small messages)
                if (req.isCompressed() && req.getPayload().length > 0) {
                    req.setPayload(decompress(req.getPayload()));
                    req.setCompressed(false);
                }

                // Decision logic: accept or reject
                boolean shouldAccept = shouldAcceptRequest(req);

                // Send handshake response with same correlationId (from transport header)
                if (correlationId != null && !correlationId.trim().isEmpty()) {
                    String response = shouldAccept ? "OK" : "REJECT";
                    sendHandshakeResponse(correlationId, response);
                }

                // If accepted, trigger RequestReceived event
                if (shouldAccept) {
                    notifyRequestReceived(req);
                }
            } catch (Exception ex) {
                notifyErrorOccurred(ex);
            }
        });
    }

    /**
     * Legacy handler for backward compatibility
     */
    private void onTransportDataReceived(byte[] message) {
        onTransportDataReceivedWithCorrelation(message, null);
    }

    /**
     * Sends a handshake response with the specified correlationId.
     * The response must use the same correlationId from the incoming request.
     * Format: [16-byte CorrelationID][Response Payload]
     */
    private void sendHandshakeResponse(String correlationId, String response) {
        if (correlationId == null || correlationId.trim().isEmpty()) {
            // Unsolicited message - no response needed
            return;
        }

        try {
            byte[] responseBytes = response.getBytes(StandardCharsets.UTF_8);
            
            // Prepend correlationId header (16 bytes) to response
            // This matches the protocol: [Length][16-byte CorrelationID][Payload]
            byte[] correlationBytes = encodeCorrelationId(correlationId);
            byte[] messageWithHeader = new byte[16 + responseBytes.length];
            System.arraycopy(correlationBytes, 0, messageWithHeader, 0, 16);
            System.arraycopy(responseBytes, 0, messageWithHeader, 16, responseBytes.length);
            
            // Send via transport (transport will add length prefix)
            transport.sendRaw(messageWithHeader);
        } catch (Exception ex) {
            notifyErrorOccurred(new IllegalStateException("Failed to send handshake response.", ex));
        }
    }

    /**
     * Encodes a correlation ID string to a 16-byte array (UTF-8, null-padded)
     */
    private byte[] encodeCorrelationId(String correlationId) {
        byte[] bytes = new byte[16];
        byte[] idBytes = correlationId.getBytes(StandardCharsets.UTF_8);
        int copyLength = Math.min(idBytes.length, 16);
        System.arraycopy(idBytes, 0, bytes, 0, copyLength);
        return bytes;
    }

    /**
     * Decision logic for accepting or rejecting incoming requests.
     * Override this method to implement custom business logic.
     */
    protected boolean shouldAcceptRequest(TransferRequest req) {
        // Default: accept all valid requests
        // Override in subclasses for custom logic
        return true;
    }

    /**
     * Handles incoming stream chunks from transport (large files).
     * Forwards chunks immediately without buffering.
     * CRITICAL FIX: Check if this is actually a TransferRequest (JSON) instead of raw data.
     * This can happen when the handshake message is routed to the stream handler.
     */
    private void onTransportStreamChunkReceived(byte[] chunk, boolean isFinal) {
        callbackExecutor.execute(() -> {
            try {
                // CRITICAL FIX: Check if this is actually a TransferRequest (JSON) instead of raw data
                // This can happen when the handshake message is routed to the stream handler
                // Check for small messages that might be JSON (regardless of isFinal flag)
                if (chunk.length < 1024 * 10) { // Small message, might be JSON
                    try {
                        String json = new String(chunk, StandardCharsets.UTF_8);
                        if (json.trim().startsWith("{") && json.contains("\"MagicBytes\"")) {
                            // This is a TransferRequest, route it to the message handler
                            onTransportDataReceivedWithCorrelation(chunk, null);
                            return;
                        }
                    } catch (Exception e) {
                        // Not JSON, continue as stream chunk
                    }
                }
                
                // NOTE: SocketTransport already strips the 16-byte correlation ID header
                // So the chunk parameter contains only the actual data (no header)
                // Create a copy for the listener (they might hold references)
                byte[] chunkCopy = new byte[chunk.length];
                System.arraycopy(chunk, 0, chunkCopy, 0, chunk.length);

                // Notify data chunk listener (for file writing)
                if (dataChunkListener != null) {
                    dataChunkListener.onDataChunkReceived(chunkCopy, isFinal);
                }

                // If final chunk, notify that transfer is complete
                if (isFinal && dataChunkListener != null) {
                    dataChunkListener.onTransferComplete();
                }
            } catch (Exception ex) {
                notifyErrorOccurred(ex);
            }
        });
    }

    @Override
    public void handleIncoming(byte[] rawData) {
        // This method is now handled by setDataReceivedListener
        // Keeping for interface compatibility
        if (rawData != null) {
            onTransportDataReceived(rawData);
        }
    }

    @Override
    public String getStatus() {
        return "regular";
    }

    @Override
    public void switchStatus(ConnectionStatus status) {
        // TODO: Implement switch status
    }

    @Override
    public void setRequestReceivedListener(IConnectionManager.RequestReceivedListener listener) {
        this.requestReceivedListener = listener;
    }

    @Override
    public void setErrorOccurredListener(IConnectionManager.ErrorOccurredListener listener) {
        this.errorOccurredListener = listener;
    }

    private byte[] compress(byte[] data) {
        try {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            try (GZIPOutputStream gzipOut = new GZIPOutputStream(baos)) {
                gzipOut.write(data);
            }
            return baos.toByteArray();
        } catch (IOException ex) {
            throw new IllegalStateException("Compression failed.", ex);
        }
    }

    private byte[] decompress(byte[] compressedData) {
        try {
            ByteArrayInputStream bais = new ByteArrayInputStream(compressedData);
            try (GZIPInputStream gzipIn = new GZIPInputStream(bais);
                 ByteArrayOutputStream baos = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[1024];
                int len;
                while ((len = gzipIn.read(buffer)) != -1) {
                    baos.write(buffer, 0, len);
                }
                return baos.toByteArray();
            }
        } catch (IOException ex) {
            throw new IllegalStateException("Decompression failed.", ex);
        }
    }

    private void notifyRequestReceived(TransferRequest req) {
        if (requestReceivedListener != null) {
            requestReceivedListener.onRequestReceived(req);
        }
    }

    private void notifyErrorOccurred(Exception ex) {
        if (errorOccurredListener != null) {
            errorOccurredListener.onErrorOccurred(ex);
        }
    }

}

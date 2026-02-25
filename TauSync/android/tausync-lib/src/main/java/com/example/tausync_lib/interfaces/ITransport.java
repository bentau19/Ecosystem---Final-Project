package com.tausync.interfaces;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

/**
 * Transport layer interface - the pipe through which bytes flow.
 * Each side (Windows/Android) must implement this for WiFi and Bluetooth.
 */
public interface ITransport {
    /**
     * Creates an initial connection to the target device.
     *
     * @param targetId The identifier of the target device to connect to.
     * @throws IllegalArgumentException If targetId is null or empty.
     * @throws IllegalStateException If connection fails.
     */
    void connect(String targetId);

    /**
     * Sends raw binary data through the transport channel (thread-safe).
     *
     * @param data The binary data to send.
     * @throws IllegalArgumentException If data is null.
     * @throws IllegalStateException If not connected or send fails.
     */
    void sendRaw(byte[] data);

    /**
     * Checks the connection status.
     *
     * @return True if connected, false otherwise.
     */
    boolean isConnected();

    /**
     * Sends a request and waits for a response with the specified correlationId.
     *
     * @param data          The data to send (will be prefixed with correlationId)
     * @param correlationId Unique identifier for request-response matching (max 16 bytes)
     * @param timeoutMs     Timeout in milliseconds
     * @return CompletableFuture that completes with the response data (without correlationId header)
     */
    CompletableFuture<byte[]> sendRequest(byte[] data, String correlationId, long timeoutMs);

    /**
     * Sets the listener for small messages (< 1MB) - legacy.
     */
    void setDataReceivedListener(DataReceivedListener listener);

    /**
     * Sets the listener for small messages with correlation ID (< 1MB).
     * Use this when you need the correlationId to send responses.
     */
    void setDataReceivedWithCorrelationListener(DataReceivedWithCorrelationListener listener);

    /**
     * Sets the listener for streaming chunks (>= 1MB).
     */
    void setStreamChunkReceivedListener(StreamChunkReceivedListener listener);

    /**
     * Listener interface for data reception events (legacy).
     */
    interface DataReceivedListener {
        void onDataReceived(byte[] data);
    }

    /**
     * Listener interface for data reception with correlation ID (for handshake responses).
     */
    interface DataReceivedWithCorrelationListener {
        /**
         * Called when data is received.
         *
         * @param data          The received data (payload only, without correlationId header)
         * @param correlationId The correlation ID from the header (null if unsolicited/all zeros)
         */
        void onDataReceived(byte[] data, String correlationId);
    }

    /**
     * Listener interface for streaming chunk events.
     */
    interface StreamChunkReceivedListener {
        /**
         * Called when a streaming chunk is received.
         *
         * @param chunk   The chunk data
         * @param isFinal True if this is the final chunk
         */
        void onStreamChunkReceived(byte[] chunk, boolean isFinal);
    }
}

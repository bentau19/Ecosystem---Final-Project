package com.tausync.interfaces;

import com.tausync.models.TransferRequest;
import com.tausync.core.ConnectionStatus;

import java.io.InputStream;
import java.util.concurrent.CompletableFuture;

/**
 * Connection management layer interface - the brain that decides which ITransport to use.
 */
public interface IConnectionManager {
    /**
     * Sends a TransferRequest with streaming data support (async).
     * Implements handshake protocol: sends metadata, waits for OK/REJECT, then streams data.
     *
     * @param dataStream The stream containing data to send
     * @param req        The transfer request metadata
     * @return CompletableFuture that completes when the transfer is finished
     * @throws IllegalArgumentException If req is null or invalid.
     * @throws IllegalStateException    If not initialized, no transport is available, or send fails.
     */
    CompletableFuture<Void> smartSend(InputStream dataStream, TransferRequest req);

    /**
     * Legacy SmartSend for backward compatibility (sends TransferRequest with payload in memory).
     *
     * @param req The transfer request with payload
     * @throws IllegalArgumentException If req is null or invalid.
     * @throws IllegalStateException    If not initialized, no transport is available, or send fails.
     */
    void smartSend(TransferRequest req);

    /**
     * Handles incoming raw data and processes it.
     *
     * @param rawData The raw binary data received.
     * @throws IllegalArgumentException If rawData is null.
     * @throws IllegalStateException    If not initialized or processing fails.
     */
    void handleIncoming(byte[] rawData);

    /**
     * Sets the listener for request received events.
     */
    void setRequestReceivedListener(RequestReceivedListener listener);

    /**
     * Sets the listener for error events.
     */
    void setErrorOccurredListener(ErrorOccurredListener listener);

    /**
     * Sets the listener for data chunks (for writing to file).
     */
    void setDataChunkListener(DataChunkListener listener);

    /**
     * Gets the current connection status.
     *
     * @return Status string
     */
    String getStatus();

    /**
     * Switches the connection status.
     *
     * @param status The new connection status
     */
    void switchStatus(ConnectionStatus status);

    /**
     * Listener interface for request received events.
     */
    interface RequestReceivedListener {
        void onRequestReceived(TransferRequest req);
    }

    /**
     * Listener interface for error events.
     */
    interface ErrorOccurredListener {
        void onErrorOccurred(Exception exception);
    }

    /**
     * Listener interface for data chunks (for writing to file).
     */
    interface DataChunkListener {
        /**
         * Called when a data chunk is received.
         *
         * @param chunk  The chunk data
         * @param isFinal True if this is the final chunk
         */
        void onDataChunkReceived(byte[] chunk, boolean isFinal);

        /**
         * Called when the transfer is complete (after final chunk).
         */
        void onTransferComplete();
    }
}

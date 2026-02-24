package com.tausync.interfaces;

import com.tausync.models.TransferRequest;
import com.tausync.core.ConnectionStatus;
/**
 * Connection management layer interface - the brain that decides which ITransport to use.
 */
public interface IConnectionManager {
    /**
     * Smart send logic that selects the appropriate transport medium and sends the request.
     *
     * @param req The transfer request to send.
     * @throws IllegalArgumentException If req is null or invalid.
     * @throws IllegalStateException If not initialized, no transport is available, or send fails.
     */
    void smartSend(TransferRequest req);

    /**
     * Handles incoming raw data and processes it.
     *
     * @param rawData The raw binary data received.
     * @throws IllegalArgumentException If rawData is null.
     * @throws IllegalStateException If not initialized or processing fails.
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

    String getStatus();
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
}

package com.example.tausync_lib.interfaces;

import java.util.concurrent.CompletableFuture;

/**
 * Transport layer — manages the physical TCP connection.
 *
 * <p>{@code connect(null)} or {@code connect("")} enters server mode (listen for
 * one client). A non-empty targetId enters client mode (connect to peer IP).
 *
 * <p>Matches C# ITransport.
 */
public interface ITransport extends AutoCloseable {

    /**
     * Establishes the transport connection with no timeout (waits indefinitely).
     *
     * @param targetId peer IP for client mode; null or empty for server mode
     * @return future that completes when the connection is established
     */
    CompletableFuture<Void> connect(String targetId);

    /**
     * Establishes the transport connection, giving up after the timeout.
     *
     * @param targetId       peer IP for client mode; null or empty for server mode
     * @param timeoutSeconds max seconds to wait for the connection; null = wait forever
     * @return future that completes when connected, or completes exceptionally with
     *         {@link java.util.concurrent.TimeoutException} when the timeout elapses
     */
    CompletableFuture<Void> connect(String targetId, Integer timeoutSeconds);

    /**
     * Sends a complete TPack frame (header + payload) over the wire.
     * Thread-safe — implementations must serialise concurrent calls.
     *
     * @param data the raw frame bytes
     * @return future that completes when the write finishes
     */
    CompletableFuture<Void> sendRaw(byte[] data);

    /**
     * @return true when the transport has an active connection
     */
    boolean isConnected();

    /**
     * Explicitly tears down the connection (intentional close): the transport does not auto-reconnect
     * after this. Implemented by both transports; declared here to match C# {@code ITransport}.
     */
    void disconnect();

    /**
     * @return true when this transport accepted a connection (server mode),
     *         false when it initiated one (client mode)
     */
    boolean isServerMode();

    /**
     * @return the physical medium this transport carries bytes over
     */
    TransportKind getTransportType();

    /**
     * Identifies which physical medium a transport carries bytes over.
     * Lets higher layers (e.g. HybridConnectionManager) tell the two transports apart.
     */
    enum TransportKind { WIFI, BLUETOOTH }

    /**
     * Registers the listener that receives unhandled control frames.
     *
     * @param listener the callback, or null to clear
     */
    void setOnDataReceivedListener(OnDataReceivedListener listener);

    /**
     * Callback for raw frames that were not handled by ConnectionContext dispatch.
     */
    @FunctionalInterface
    interface OnDataReceivedListener {
        void onDataReceived(byte[] data);
    }
}

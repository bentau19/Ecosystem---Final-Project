package com.tausync.interfaces;

import java.util.concurrent.CompletableFuture;

/**
 * Transport layer interface — manages the physical connection.
 * Per TauSync Protocol Spec: raw bytes only; framing and reassembly are transport's responsibility.
 * Matches C# ITransport: Connect (null/empty = server mode), SendRaw, IsConnected, OnDataReceived.
 */
public interface ITransport extends AutoCloseable {

    /**
     * Connects to the target. When targetId is null or empty, acts as server: listens and waits for the first incoming connection.
     *
     * @param targetId IP address of the peer (client mode), or null/empty for server mode.
     * @return CompletableFuture that completes when connected.
     */
    CompletableFuture<Void> connect(String targetId);

    /**
     * Sends raw binary data (full TPack: 8-byte header + payload). No extra length prefix.
     *
     * @param data The complete TPack to send.
     * @return CompletableFuture that completes when send is done.
     */
    CompletableFuture<Void> sendRaw(byte[] data);

    /**
     * Returns the current connection status.
     */
    boolean isConnected();

    /**
     * Sets the listener invoked when a complete TPack has been received (after reassembly: 8-byte header + Length bytes payload).
     */
    void setOnDataReceivedListener(OnDataReceivedListener listener);

    /**
     * Listener for complete TPack reception.
     */
    @FunctionalInterface
    interface OnDataReceivedListener {
        void onDataReceived(byte[] data);
    }
}

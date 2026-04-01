package com.example.tausync_lib;

import com.example.tausync_lib.implementations.management.ConnectionContext;
import com.example.tausync_lib.implementations.management.ConnectionManager;
import com.example.tausync_lib.implementations.management.TauSyncStream;

import java.util.concurrent.CompletableFuture;

/**
 * High-level entry point for TauSync on Android.
 * Wraps ConnectionContext and ConnectionManager into a simple API.
 */
public class TauSyncJavaEngine {

    private ConnectionManager manager;

    /**
     * Starts listening for incoming connections (server mode).
     *
     * @return future that completes when a peer connects
     */
    public CompletableFuture<Void> listen() {
        return CompletableFuture.runAsync(() -> {
            try {
                ConnectionContext.getInstance().initializeTransports(null);
                manager = new ConnectionManager();
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        });
    }

    /**
     * Connects to a peer at the given IP (client mode).
     *
     * @param ip the peer's IP address
     * @return future that completes when connected
     */
    public CompletableFuture<Void> connectTo(String ip) {
        return CompletableFuture.runAsync(() -> {
            try {
                ConnectionContext.getInstance().initializeTransports(ip);
                manager = new ConnectionManager();
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        });
    }

    /**
     * Opens a bidirectional channel using a Meeting Word.
     *
     * @param word the Meeting Word to connect on
     * @return future containing the stream
     */
    public CompletableFuture<TauSyncStream> connect(String word) {
        if (manager == null) {
            return CompletableFuture.failedFuture(
                    new IllegalStateException("Call listen() or connectTo() first."));
        }
        return manager.connect(word);
    }

    /**
     * @return true when the transport layer has an active connection
     */
    public boolean isConnected() {
        return manager != null && manager.isConnected();
    }

    /**
     * Creates an additional ConnectionManager sharing the same transport.
     *
     * @return a new ConnectionManager instance
     */
    public ConnectionManager newManager() {
        if (manager == null) {
            throw new IllegalStateException("Call listen() or connectTo() first.");
        }
        return new ConnectionManager();
    }
}

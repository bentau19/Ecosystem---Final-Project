package com.example.tausync_lib.sdk;

import android.util.Log;

import com.example.tausync_lib.implementations.management.ConnectionContext;
import com.example.tausync_lib.implementations.management.ConnectionManager;
import com.example.tausync_lib.implementations.management.TauSyncStream;

import java.util.Objects;
import java.util.concurrent.TimeUnit;

/**
 * High-level entry point for TauSync on Android.
 *
 * <p>Mirrors the Python {@code tausync_py.TauSync} API:
 * <pre>{@code
 * TauSync tau = new TauSync();
 * tau.connectTo("192.168.1.100");
 * TauSyncStream stream = tau.connect("main");
 * stream.writeString("Hello!\n");
 * String reply = stream.readLine();
 * stream.close();
 * tau.dispose();
 * }</pre>
 *
 * <p>The underlying transport is a process-wide singleton. Only one role
 * (server or client) can be active at a time. Multiple {@link TauSync}
 * instances share the same socket via {@link #newManager()}.
 */
public final class TauSync {

    private static final int ROLE_NONE = 0;
    private static final int ROLE_SERVER = 1;
    private static final int ROLE_CLIENT = 2;

    private static final Object roleLock = new Object();
    private static volatile int globalRole = ROLE_NONE;
    private static volatile String globalTarget = null;

    private ConnectionManager manager;
    private volatile boolean disposed;

    /**
     * Starts listening for incoming connections (server mode, blocking).
     *
     * <p>Blocks until a remote peer connects on the default port (8888).
     * Only needs to be called once per process -- the underlying transport
     * is a singleton.
     *
     * @throws IllegalStateException if the transport is already in client mode
     *                               or this instance is disposed
     */
    public void listen() {
        checkNotDisposed();
        synchronized (roleLock) {
            if (globalRole == ROLE_CLIENT) {
                throw new IllegalStateException(
                        "Cannot listen() -- transport is already connected in client mode "
                                + "(to " + globalTarget + "). The transport is a singleton; "
                                + "you cannot switch roles.");
            }
            if (globalRole == ROLE_SERVER) return;
            globalRole = ROLE_SERVER;
            globalTarget = "0.0.0.0 (listening)";
        }

        try {
            ConnectionContext.getInstance().initializeTransports(null);
            manager = new ConnectionManager();
        } catch (Exception e) {
            synchronized (roleLock) {
                globalRole = ROLE_NONE;
                globalTarget = null;
            }
            throw new RuntimeException("Failed to start listening", e);
        }
    }

    /**
     * Connects to a remote TauSync server (client mode, blocking).
     *
     * <p>Blocks until the TCP connection is established. Retries
     * automatically every 2 seconds until success.
     *
     * @param ip the server's IP address (e.g. "192.168.1.100")
     * @throws IllegalArgumentException if ip is null or blank
     * @throws IllegalStateException    if the transport is already in server mode,
     *                                  already connected to a different IP, or disposed
     */
    public void connectTo(String ip) {
        checkNotDisposed();
        if (ip == null || ip.trim().isEmpty()) {
            throw new IllegalArgumentException("ip must not be null or blank");
        }
        String trimmed = ip.trim();

        synchronized (roleLock) {
            if (globalRole == ROLE_SERVER) {
                throw new IllegalStateException(
                        "Cannot connectTo() -- transport is already in server mode. "
                                + "The transport is a singleton; you cannot switch roles.");
            }
            if (globalRole == ROLE_CLIENT) {
                if (!trimmed.equals(globalTarget)) {
                    throw new IllegalStateException(
                            "Cannot connectTo(\"" + trimmed + "\") -- already connected to "
                                    + globalTarget + ". The transport is a singleton.");
                }
                if (manager == null) manager = new ConnectionManager();
                return;
            }
            globalRole = ROLE_CLIENT;
            globalTarget = trimmed;
        }

        try {
            ConnectionContext.getInstance().initializeTransports(trimmed);
            manager = new ConnectionManager();
        } catch (Exception e) {
            synchronized (roleLock) {
                globalRole = ROLE_NONE;
                globalTarget = null;
            }
            throw new RuntimeException("Failed to connect to " + trimmed, e);
        }
    }

    /**
     * Opens a named duplex channel using a Meeting Word (blocking).
     *
     * <p>Both sides must call {@code connect(word)} with the same word;
     * they are paired automatically and each gets a private
     * {@link TauSyncStream}.
     *
     * @param word the Meeting Word (case-sensitive, e.g. "main")
     * @return a bidirectional stream for reading and writing
     * @throws IllegalArgumentException if word is null or blank
     * @throws IllegalStateException    if not connected or disposed
     */
    public TauSyncStream connect(String word) {
        return connect(word, 30);
    }

    /**
     * Opens a named duplex channel with a custom timeout.
     *
     * @param word       the Meeting Word
     * @param timeoutSec max seconds to wait for the handshake
     * @return a bidirectional stream
     */
    public TauSyncStream connect(String word, int timeoutSec) {
        checkNotDisposed();
        if (word == null || word.trim().isEmpty()) {
            throw new IllegalArgumentException("word must not be null or blank");
        }
        if (globalRole == ROLE_NONE) {
            throw new IllegalStateException(
                    "Cannot connect() -- transport is not established. "
                            + "Call listen() or connectTo() first.");
        }
        if (manager == null) {
            throw new IllegalStateException("Manager not initialized.");
        }

        try {
            return manager.connect(word).get(timeoutSec, TimeUnit.SECONDS);
        } catch (Exception e) {
            throw new RuntimeException("connect(\"" + word + "\") failed", e);
        }
    }

    /**
     * @return true when the transport layer has an active connection
     */
    public boolean isConnected() {
        return manager != null && manager.isConnected();
    }

    /**
     * Creates another {@link TauSync} instance sharing the same transport.
     *
     * <p>Useful for opening channels from multiple independent managers
     * on the same underlying socket.
     *
     * @return a new TauSync instance with its own ConnectionManager
     * @throws IllegalStateException if transport is not established
     */
    public TauSync newManager() {
        checkNotDisposed();
        if (globalRole == ROLE_NONE) {
            throw new IllegalStateException("Call listen() or connectTo() first.");
        }
        TauSync other = new TauSync();
        other.manager = new ConnectionManager();
        return other;
    }

    /**
     * Snapshot of words the peer is waiting on but we have not paired with
     * locally. Mirrors C# {@code TauSync.GetPeerWaitingWords}.
     *
     * @return immutable list of peer-waiting words (uppercased on this side)
     * @throws IllegalStateException if this instance is disposed
     */
    public java.util.List<String> getPeerWaitingWords() {
        checkNotDisposed();
        return manager.getPeerWaitingWords();
    }

    /**
     * Disposes the underlying ConnectionManager.
     * Safe to call multiple times.
     */
    public void dispose() {
        if (disposed) return;
        disposed = true;
        if (manager != null) {
            try {
                manager.close();
            } catch (Exception ignored) {
            }
        }
    }

    private void checkNotDisposed() {
        if (disposed) {
            throw new IllegalStateException("This TauSync instance has been disposed.");
        }
    }
}

package com.example.tausync_lib.sdk;

import static android.content.ContentValues.TAG;

import android.util.Log;

import com.example.tausync_lib.core.CoreConfig;
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
     * Starts listening for incoming connections (server mode, blocking, no timeout).
     *
     * <p>Blocks until a remote peer connects on the default port (8888).
     * Only needs to be called once per process -- the underlying transport
     * is a singleton.
     *
     * @throws IllegalStateException if the transport is already in client mode
     *                               or this instance is disposed
     */
    public void listen() {
        listen(null);
    }

    /**
     * Starts listening for incoming connections (server mode, blocking).
     *
     * @param timeoutSeconds max seconds to wait for a client; null = wait forever
     * @throws RuntimeException      wrapping {@link java.util.concurrent.TimeoutException}
     *                               when no client connects within the timeout
     * @throws IllegalStateException if the transport is already in client mode
     *                               or this instance is disposed
     */
    public void listen(Integer timeoutSeconds) {
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
            ConnectionContext.getInstance().initializeTransports(null, timeoutSeconds);
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
     * Connects to a remote TauSync server (client mode, blocking, no timeout).
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
        connectTo(ip, null);
    }

    /**
     * Connects to a remote TauSync server (client mode, blocking).
     *
     * <p>Retries automatically every 2 seconds until success or until the
     * timeout elapses. Each individual TCP attempt is also bounded by the
     * remaining budget, so a black-holed IP cannot overrun the timeout.
     *
     * @param ip             the server's IP address (e.g. "192.168.1.100")
     * @param timeoutSeconds max seconds to keep retrying; null = retry forever
     * @throws RuntimeException         wrapping {@link java.util.concurrent.TimeoutException}
     *                                  when the timeout elapses before connecting
     * @throws IllegalArgumentException if ip is null or blank
     * @throws IllegalStateException    if the transport is already in server mode,
     *                                  already connected to a different IP, or disposed
     */
    public void connectTo(String ip, Integer timeoutSeconds) {
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
            ConnectionContext.getInstance().initializeTransports(trimmed, timeoutSeconds);
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
        return connect(word, CoreConfig.HANDSHAKE_TIMEOUT_SECONDS);
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
            // Pass timeoutSec into the manager so the internal ownPath/peerPath race
            // uses the caller's budget, not the hardcoded CoreConfig.HANDSHAKE_TIMEOUT_SECONDS.
            // Both race paths share a single wall-clock budget armed at race start
            // (see ConnectionManager.resolveConnectRaceAsync), so the worst case is
            // ~timeoutSec; the 5-second buffer on the outer get() ensures the inner
            // future expires first and its cleanup (unregisterService, word-channel
            // removal, attempt release) always runs.
            return manager.connect(word, timeoutSec).get(timeoutSec + 5L, TimeUnit.SECONDS);
        } catch (Exception e) {
            Log.d(TAG, "connect: timeout is:" + timeoutSec);
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
     * Closes the TCP transport and resets the process-wide role so that
     * {@link #connectTo(String)} or {@link #listen()} can be called again on
     * this instance (or a new one).
     *
     * <p>Unlike {@link #dispose()}, this instance is NOT marked as permanently
     * dead after this call. Safe to call when already disconnected (no-op if
     * the instance is disposed).
     *
     * <p>Mirrors the Python {@code tausync_py.TauSync.disconnect()} contract.
     */
    public void disconnect() {
        if (disposed) return;

        // 1. Close the TCP socket. SocketTransport.disconnect() closes streams/socket
        //    but does NOT set disposed=true, so the transport can accept a new connection.
        ConnectionContext.getInstance().getWifiTransportAsSocket().disconnect();

        // 2. Clear all in-flight routing, service registry, and pending discovery
        //    frames so the next connection starts from a clean state.
        ConnectionContext.getInstance().reset();

        // 3. Close and release the ConnectionManager.
        if (manager != null) {
            try {
                manager.close();
            } catch (Exception ignored) {
            }
            manager = null;
        }

        // 4. Reset global role so connectTo()/listen() can proceed on the next call.
        synchronized (roleLock) {
            globalRole = ROLE_NONE;
            globalTarget = null;
        }
    }

    /**
     * Permanently disposes this instance and the underlying ConnectionManager.
     * Safe to call multiple times.
     *
     * <p>Also resets the process-wide role, mirroring Python {@code tausync_py.TauSync.dispose()}.
     * Create a new {@link TauSync} instance if you need to reconnect after disposal.
     */
    public void dispose() {
        if (disposed) return;
        disposed = true;

        // Close socket and clear session state (same as disconnect, but instance is now dead).
        ConnectionContext.getInstance().getWifiTransportAsSocket().disconnect();
        ConnectionContext.getInstance().reset();

        if (manager != null) {
            try {
                manager.close();
            } catch (Exception ignored) {
            }
        }

        // Reset global role so a new TauSync() created afterwards can connect.
        synchronized (roleLock) {
            globalRole = ROLE_NONE;
            globalTarget = null;
        }
    }

    private void checkNotDisposed() {
        if (disposed) {
            throw new IllegalStateException("This TauSync instance has been disposed.");
        }
    }
}

package com.example.tausync_lib.interfaces;

import com.example.tausync_lib.implementations.management.TauSyncStream;

import java.util.concurrent.CompletableFuture;

/**
 * Public API consumed by applications per TauSync v3.
 *
 * <p>Both sides call {@link #connect(String)} with the same Meeting Word;
 * they are paired and each gets a bidirectional {@link TauSyncStream}.
 * Matches C# IConnectionManager.
 */
public interface IConnectionManager extends AutoCloseable {

    /**
     * Binds this manager to a transport. Called once.
     *
     * @param transport the transport to use
     * @throws IllegalArgumentException if transport is null
     * @throws IllegalStateException    if already initialised
     */
    void initialize(ITransport transport);

    /**
     * Establishes the underlying TCP connection with no timeout.
     * Delegates to {@code ConnectionContext.initializeTransports}.
     *
     * @param targetId peer IP for client mode; null/empty for server mode
     * @return future that completes when connected
     */
    CompletableFuture<Void> connectTransport(String targetId);

    /**
     * Establishes the underlying TCP connection, giving up after the timeout.
     * Mirrors C# {@code ConnectTransport(targetId, timeoutSeconds)}.
     *
     * @param targetId       peer IP for client mode; null/empty for server mode
     * @param timeoutSeconds max seconds to wait; null = wait forever
     * @return future that completes when connected, or completes exceptionally with
     *         {@link java.util.concurrent.TimeoutException} when the timeout elapses
     */
    CompletableFuture<Void> connectTransport(String targetId, Integer timeoutSeconds);

    /**
     * @return true when the transport has an active connection
     */
    boolean isConnected();

    /**
     * Symmetric connect — both sides call with the same word.
     *
     * @param word the Meeting Word (case-insensitive)
     * @return future containing a bidirectional stream
     * @throws IllegalArgumentException if word is null or blank
     * @throws IllegalStateException    if transport not connected or manager disposed
     */
    CompletableFuture<TauSyncStream> connect(String word);

    /**
     * Same as {@link #connect(String)} but uses a caller-supplied handshake timeout
     * instead of {@code CoreConfig.HANDSHAKE_TIMEOUT_SECONDS}.
     *
     * @param word       the Meeting Word
     * @param timeoutSec seconds to wait for the peer to call {@code connect(word)} before
     *                   the internal ownPath / peerPath race resolution gives up
     * @return future containing a bidirectional stream
     */
    CompletableFuture<TauSyncStream> connect(String word, int timeoutSec);

    /**
     * Sends data over an existing stream channel.
     *
     * @param localId the local stream ID
     * @param buffer  source byte array
     * @param offset  start position in buffer
     * @param count   number of bytes to send
     * @throws IllegalStateException if no peer route exists for localId
     */
    void sendStreamData(int localId, byte[] buffer, int offset, int count);

    /**
     * Async variant of {@link #sendStreamData(int, byte[], int, int)}.
     */
    CompletableFuture<Void> sendStreamDataAsync(int localId, byte[] buffer, int offset, int count);

    /**
     * Sends FIN and releases the local ID.
     *
     * @param localId the local stream ID to complete
     */
    void completeStream(int localId);

    /**
     * Registers a listener for errors that occur during handshake or I/O.
     *
     * @param listener the callback, or null to clear
     */
    void setErrorListener(ErrorListener listener);

    @FunctionalInterface
    interface ErrorListener {
        void onError(Exception error);
    }
}

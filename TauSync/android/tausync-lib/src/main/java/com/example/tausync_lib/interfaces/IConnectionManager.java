package com.tausync.interfaces;

import com.example.tausync_lib.models.TransferRequest;

import java.io.InputStream;
import java.util.concurrent.CompletableFuture;
import java.util.function.Consumer;

/**
 * Connection manager — which connection and when; dispatcher and routing map.
 * Routes incoming TPack by CorrelationID to registered handlers. Control channel = 0.
 * Per TauSync Protocol Spec. Matches C# IConnectionManager.
 */
public interface IConnectionManager extends AutoCloseable {

    /**
     * Sets the listener for incoming CLIPBOARD push from the peer (e.g. Windows).
     * When the peer sends PUSH with Type=CLIPBOARD, the received text is passed to this callback.
     */
    void setOnClipboardReceivedListener(ClipboardReceivedListener listener);

    /**
     * Listener for received clipboard content (incoming PUSH CLIPBOARD).
     */
    @FunctionalInterface
    interface ClipboardReceivedListener {
        void onClipboardReceived(String text);
    }

    /**
     * Initializes the manager with the transport to use. Use this when the caller provides the transport.
     * Alternatively, use {@link #connect(String)} to let the manager create and own the transport.
     */
    void initialize(ITransport transport);

    /**
     * Connects to the target by creating and managing the transport internally.
     * Pass null or empty targetId for server mode (wait for incoming connection).
     *
     * @param targetId Target address (client mode), or null/empty for server mode.
     * @return CompletableFuture that completes when connected.
     */
    CompletableFuture<Void> connect(String targetId);

    /**
     * Returns whether the underlying transport is connected.
     */
    boolean isConnected();

    /**
     * Pushes data: handshake on channel 0, then streams content on a dedicated CorrelationID.
     *
     * @param source  Stream to read from (e.g. clipboard content).
     * @param type    Task type (e.g. "CLIPBOARD").
     * @param payload Optional JSON (e.g. {"FileName": "x"}). May be null.
     * @return CompletableFuture that completes when the transfer is finished.
     */
    CompletableFuture<Void> smartSend(InputStream source, String type, String payload);

    /**
     * Pulls data: double handshake on channel 0, then returns a stream fed by incoming TPack for the agreed CorrelationID.
     *
     * @param type    Task type (e.g. "BACKUP").
     * @param payload Optional JSON. May be null.
     * @return CompletableFuture that completes with a stream ready for read.
     */
    CompletableFuture<InputStream> getStream(String type, String payload);

    /**
     * Registers a handler for a CorrelationID. When a TPack arrives with that ID, payload is passed to the callback.
     */
    void registerHandler(int correlationId, Consumer<byte[]> callback);

    /**
     * Unregisters the handler for the given CorrelationID (e.g. after FIN or error).
     */
    void unregisterHandler(int correlationId);

    /**
     * Sets the listener for errors (e.g. handshake timeout, reject, dispatch failure).
     */
    void setErrorOccurredListener(ErrorOccurredListener listener);

    /**
     * Listener for errors.
     */
    @FunctionalInterface
    interface ErrorOccurredListener {
        void onErrorOccurred(Exception exception);
    }
}

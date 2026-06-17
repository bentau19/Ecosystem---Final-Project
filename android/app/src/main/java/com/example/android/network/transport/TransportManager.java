package com.example.android.network.transport;

import com.example.android.domain.entities.RemoteDeviceInfo;
import java.util.List;

/**
 * TransportManager interface defines the contract for managing communication with a remote device.
 *
 * This interface abstracts away the specific transport mechanism (WiFi, Bluetooth, P2P, etc.)
 * and provides a unified API for:
 * - Establishing and maintaining connections
 * - Reading/writing from data channels
 * - Managing connection state and lifecycle
 * - Providing automatic reconnection capability
 * - Handling peer-requested commands
 *
 * This design allows for:
 * ✓ Easy addition of new transport types (Bluetooth, P2P, etc.)
 * ✓ Testing with mock implementations
 * ✓ Decoupling ConnectivityService from TauSync specifics
 */
public interface TransportManager {

    /**
     * Listener for transport-level events and state changes.
     */
    interface TransportListener {
        /**
         * Called when connection status changes.
         */
        void onStatusChanged(TransportStatus status);

        /**
         * Called when peer has requests available on specific channels.
         */
        void onPeerRequestsAvailable(List<String> channels);

        /**
         * Called when a connection error occurs.
         */
        void onConnectionError(Exception error);

        /**
         * Called when the transport is about to attempt reconnection.
         */
        void onReconnectAttempt(int attemptNumber, int maxRetries);
    }

    /**
     * Callback for {@link #serveJsonExchange(String, JsonExchangeHandler)}: given the peer's
     * newline-terminated JSON request string, computes and returns the JSON response string.
     */
    @FunctionalInterface
    interface JsonExchangeHandler {
        /**
         * @param request The newline-terminated JSON request read from the channel.
         * @return The JSON response string to write back on the same channel.
         * @throws Exception if computing the response fails.
         */
        String respond(String request) throws Exception;
    }

    /**
     * Connects to the remote device with automatic reconnection support.
     *
     * @param remoteDevice Information about the target remote device
     * @param listener Callback for transport events
     */
    void connect(RemoteDeviceInfo remoteDevice, TransportListener listener);

    /**
     * Disconnects gracefully from the remote device.
     */
    void disconnect();

    /**
     * Writes data to a specific channel using the default 30-second connect timeout.
     *
     * @param channel Channel name (e.g., "battery_level", "pc_name")
     * @param data Data to write
     * @throws Exception if write fails
     */
    void writeToChannel(String channel, String data) throws Exception;

    /**
     * Same as {@link #writeToChannel(String, String)} but uses a caller-supplied connect
     * timeout instead of the default 30 s.
     *
     * <p>Use when you need a shorter deadline — e.g. a best-effort disconnect signal where
     * waiting 30 s for the peer to join would visibly stall the UI.
     *
     * @param channel    Channel name
     * @param data       Data to write
     * @param timeoutSec Seconds to wait for the peer to join the channel
     * @throws Exception if the connect times out or the write fails
     */
    void writeToChannel(String channel, String data, int timeoutSec) throws Exception;

    /**
     * Reads data from a specific channel (non-blocking).
     *
     * @param channel Channel name
     * @return Data from the channel, or empty string if no data available
     * @throws Exception if read fails
     */
    String readFromChannel(String channel) throws Exception;

    /**
     * Same as {@link #readFromChannel(String)} but uses a caller-supplied TauSync connect
     * timeout instead of the default 30 s.
     *
     * <p>Use when the peer may take longer than 30 s to open the same channel — e.g.
     * a backup result channel where the PC needs time to classify and copy the file
     * before sending the result.
     *
     * @param channel           Channel name (e.g. {@code "backup_file_result_3"})
     * @param connectTimeoutSec Seconds to wait for the peer to call {@code connect()}
     * @return UTF-8 string payload written by the peer
     * @throws Exception if the connect times out or the read fails
     */
    String readFromChannel(String channel, int connectTimeoutSec) throws Exception;

    /**
     * Reads raw bytes from a channel.
     * Used for binary data (file contents) where String conversion would corrupt the data.
     *
     * @param channel Channel name
     * @return Raw byte array, or empty array if not connected / on error
     * @throws Exception if read fails
     */
    byte[] readBytesFromChannel(String channel) throws Exception;

    /**
     * Streams bytes from a channel directly into the provided OutputStream.
     * Reads in 64 KB chunks until the peer closes the channel (EOF/FIN).
     * No full-file buffering in RAM — safe for arbitrarily large files.
     *
     * @param channel      Channel name (e.g. "file_data_pc")
     * @param outputStream Destination stream (e.g. opened via MediaStore)
     * @throws Exception if the channel read or the write to outputStream fails
     */
    void streamChannelToOutputStream(String channel, java.io.OutputStream outputStream) throws Exception;

    /**
     * Streams bytes from the provided InputStream into a TauSync channel.
     * Reads from {@code inputStream} in 64 KB chunks and writes each chunk to the
     * channel until the stream is exhausted (EOF).
     * No full-file buffering in RAM — safe for arbitrarily large files.
     *
     * @param channel     Channel name (e.g. "file_data_android")
     * @param inputStream Source stream (e.g. opened via ContentResolver for a URI)
     * @throws Exception if the channel write or the read from inputStream fails
     */
    void streamInputStreamToChannel(String channel, java.io.InputStream inputStream) throws Exception;

    /**
     * Same as {@link #streamInputStreamToChannel(String, java.io.InputStream)} but with a
     * caller-supplied TauSync connect timeout.
     *
     * <p>Use for channels where the peer may take longer than the default 30 s to call
     * {@code connect()} — e.g. backup data slots whose file-size-proportional timeout
     * can greatly exceed 30 s for large files. The timeout governs only the
     * <em>meeting handshake</em> (waiting for the peer to open the same channel);
     * the actual byte-streaming phase is not time-bounded.
     *
     * @param channel           Channel name (e.g. {@code "backup_slot_data_3"})
     * @param inputStream       Source stream (e.g. opened via ContentResolver for a URI)
     * @param connectTimeoutSec Seconds to wait for the peer to call {@code connect()} on
     *                          the same channel before throwing
     * @throws Exception if the connect times out, or the channel write / stream read fails
     */
    void streamInputStreamToChannel(String channel,
                                    java.io.InputStream inputStream,
                                    int connectTimeoutSec) throws Exception;

    /**
     * Opens a single TauSync channel, writes a UTF-8 metadata string followed by a
     * newline delimiter ({@code '\n'}), then streams all bytes from {@code inputStream}.
     * Closes the channel after the stream is exhausted.
     *
     * <p>Used by the backup slot protocol so the PC can read the per-file metadata
     * ({@code file_name}, {@code file_size}, {@code modified_at}) before receiving the
     * raw file bytes — all in one {@code tauSync.connect()}, avoiding the 2-second
     * ID-recycling grace period that would occur if metadata and bytes were sent in
     * two separate channel connections.
     *
     * <p>The {@code '\n'} delimiter is safe because well-formed JSON never contains a
     * bare newline character.
     *
     * @param channel     Channel name (e.g. {@code "backup_slot_data_0"})
     * @param metadata    UTF-8 JSON string; must not contain a bare {@code '\n'}
     * @param inputStream Source of raw file bytes
     * @throws Exception if the channel connect, metadata write, or byte stream fails
     */
    void writeMetadataThenStreamToChannel(String channel,
                                          String metadata,
                                          java.io.InputStream inputStream) throws Exception;

    /**
     * Opens a single TauSync channel, reads one newline-terminated JSON request from the peer,
     * passes it to {@code handler}, and writes the handler's JSON response back on the same
     * channel before closing it.
     *
     * <p>Used by the virtual-drive protocol for simple metadata ops: the desktop opens a
     * unique meeting word (e.g. {@code "virtual_drive_stat_a1b2c3d4"}), writes a JSON
     * request line, and reads the JSON response.
     *
     * @param channel Channel name (meeting word) to serve.
     * @param handler Computes the JSON response from the JSON request.
     * @throws Exception if the channel connect, read, handler, or write fails.
     */
    void serveJsonExchange(String channel, JsonExchangeHandler handler) throws Exception;

    /**
     * Callback for {@link #serveJsonThenStreamOut}: given the peer's newline-terminated
     * JSON request string, opens and returns the {@link java.io.InputStream} whose bytes
     * will be streamed back to the peer on the same channel.
     *
     * <p>The returned stream is closed by the transport after all bytes have been sent.
     */
    @FunctionalInterface
    interface JsonToInputStreamHandler {
        /**
         * @param jsonRequest The newline-terminated JSON request read from the channel.
         * @return An open {@link java.io.InputStream} to stream back to the peer.
         * @throws Exception if opening the source stream fails.
         */
        java.io.InputStream openInputStream(String jsonRequest) throws Exception;
    }

    /**
     * Opens a single TauSync channel, reads one newline-terminated JSON request from the
     * peer, calls {@code handler} to obtain a source {@link java.io.InputStream}, and
     * streams all bytes from that stream back to the peer before closing the channel.
     *
     * <p>Used by the virtual-drive {@code read} op: the desktop opens
     * {@code virtual_drive_read_{uuid8}}, writes {@code {path, offset, length}\n}, and
     * reads the file bytes back. Android reads the request, opens the file range via the
     * handler, then streams the bytes until EOF. The handler's stream is closed by
     * this method via try-with-resources.
     *
     * @param channel Channel name (meeting word) to serve.
     * @param handler Opens the source byte stream for the given JSON request.
     * @throws Exception if the channel connect, JSON read, handler, stream, or write fails.
     */
    void serveJsonThenStreamOut(String channel, JsonToInputStreamHandler handler) throws Exception;

    /**
     * Callback for {@link #serveJsonHeaderThenStreamIn}: given the peer's newline-terminated
     * JSON header string, opens and returns the {@link java.io.OutputStream} into which the
     * remaining bytes from the peer will be piped.
     *
     * <p>The returned stream is closed by the transport after all peer bytes have been written.
     * The caller is responsible for any post-close finalization (e.g. renaming a temp file).
     */
    @FunctionalInterface
    interface JsonHeaderThenStreamInHandler {
        /**
         * @param jsonHeader The newline-terminated JSON header read from the channel.
         * @return An open {@link java.io.OutputStream} to receive the byte stream.
         * @throws Exception if opening the destination stream fails.
         */
        java.io.OutputStream openOutputStream(String jsonHeader) throws Exception;
    }

    /**
     * Opens a single TauSync channel, reads one newline-terminated JSON header from the
     * peer, calls {@code handler} to obtain a destination {@link java.io.OutputStream},
     * and pipes all remaining bytes from the channel into that stream until the peer closes
     * it (EOF / FIN). The handler's stream is then closed via try-with-resources.
     *
     * <p>Used by the virtual-drive {@code write} op: the desktop opens
     * {@code virtual_drive_write_{uuid8}}, writes {@code {path}\n} then pushes the file
     * bytes across multiple internal pipe writes, and finally closes the stream on
     * {@code write_close}. Android reads the path from the header, opens a temp
     * {@link java.io.FileOutputStream} via the handler, and receives all bytes. After
     * this method returns the temp file is fully written and closed; the caller should
     * call {@code finalizeWrite(path)} to atomically rename it.
     *
     * @param channel Channel name (meeting word) to serve.
     * @param handler Opens the destination byte stream for the given JSON header.
     * @throws Exception if the channel connect, JSON read, handler, stream, or write fails.
     */
    void serveJsonHeaderThenStreamIn(String channel, JsonHeaderThenStreamInHandler handler) throws Exception;

    /**
     * Stops the polling loop and transitions the transport to DISCONNECTING,
     * <em>without</em> closing the underlying socket or resetting the retry state.
     *
     * <p>Call this before {@link #writeToChannel} when sending a disconnect signal so
     * the polling executor (which fires every 20 ms) can no longer race with the
     * outbound {@code tauSync.connect()} call.  If the poll were allowed to fail
     * concurrently, {@code handlePollingFailure} would dispose the socket before the
     * desktop has a chance to join the {@code disconnect_phone} meeting word, stalling
     * Android for up to 30 seconds (the {@code writeToChannel} connect timeout).
     *
     * <p>This method blocks briefly (up to 5 s) waiting for any in-flight polling task
     * to complete, then returns with polling fully stopped.  Call it from a background
     * thread — never from the main thread.
     */
    void prepareForDisconnect();

    /**
     * Checks if the transport is currently connected.
     */
    boolean isConnected();

    /**
     * Gets the current connection status.
     */
    TransportStatus getStatus();

    /**
     * Gracefully stops the transport and releases all resources.
     */
    void shutdown();
}


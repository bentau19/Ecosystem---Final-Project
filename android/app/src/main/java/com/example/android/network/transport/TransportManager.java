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
     * Writes data to a specific channel.
     *
     * @param channel Channel name (e.g., "battery_level", "pc_name")
     * @param data Data to write
     * @throws Exception if write fails
     */
    void writeToChannel(String channel, String data) throws Exception;

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


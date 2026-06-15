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
     * Callback used by {@link #serveJsonExchange} to transform a peer's JSON
     * request into a JSON response — all on the same underlying TauSyncStream.
     */
    @FunctionalInterface
    interface JsonExchangeHandler {
        /**
         * @param requestJson Raw JSON string written by the peer.
         * @return JSON string to write back as the response.
         * @throws Exception if the request cannot be processed.
         */
        String respond(String requestJson) throws Exception;
    }

    /**
     * Serves a single PC-initiated JSON request-response exchange on one TauSyncStream.
     *
     * <p>Opens the channel, reads the full JSON string sent by the peer, invokes
     * {@code handler} with that string, writes the handler's return value as the
     * response, then closes the stream — all within the same TauSync channel ID.
     *
     * <p>This is required for virtual-drive channels where the PC writes a request
     * and blocks waiting for the response on the <em>same</em> stream.  Using
     * separate {@link #readFromChannel} / {@link #writeToChannel} calls would open
     * two independent streams and break the protocol.
     *
     * <p>Must be called from a background thread — blocks until the exchange
     * is complete.
     *
     * @param channel Meeting word the peer is blocking on.
     * @param handler Transforms the request JSON into the response JSON.
     * @throws Exception if the channel cannot be opened, the read fails,
     *                   the handler throws, or the write fails.
     */
    void serveJsonExchange(String channel, JsonExchangeHandler handler) throws Exception;

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


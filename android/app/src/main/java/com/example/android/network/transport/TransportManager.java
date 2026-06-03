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


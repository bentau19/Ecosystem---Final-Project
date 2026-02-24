package com.tausync.interfaces;

/**
 * Transport layer interface - the pipe through which bytes flow.
 * Each side (Windows/Android) must implement this for WiFi and Bluetooth.
 */
public interface ITransport {
    /**
     * Creates an initial connection to the target device.
     *
     * @param targetId The identifier of the target device to connect to.
     * @throws IllegalArgumentException If targetId is null or empty.
     * @throws IllegalStateException If connection fails.
     */
    void connect(String targetId);

    /**
     * Sends raw binary data through the transport channel.
     *
     * @param data The binary data to send.
     * @throws IllegalArgumentException If data is null.
     * @throws IllegalStateException If not connected or send fails.
     */
    void sendRaw(byte[] data);

    /**
     * Checks the connection status.
     *
     * @return True if connected, false otherwise.
     */
    boolean isConnected();

    /**
     * Sets the listener for data reception events.
     */
    void setDataReceivedListener(DataReceivedListener listener);

    /**
     * Listener interface for data reception events.
     */
    interface DataReceivedListener {
        void onDataReceived(byte[] data);
    }
}

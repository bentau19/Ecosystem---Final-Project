package com.example.android.domain.enums;

/**
 * Represents the current state of the connection to a remote PC.
 * Used by the Repository and Service to track connection lifecycle.
 *
 * States:
 * - DISCONNECTED: No active connection
 * - CONNECTING: Attempting to establish connection
 * - CONNECTED: Successfully connected and actively communicating
 * - RECONNECTING: Lost connection, automatically attempting to reconnect
 * - FAILED: Connection failed after retries exhausted
 */
public enum ConnectionStatus {
    DISCONNECTED("Disconnected"),
    CONNECTING("Connecting..."),
    CONNECTED("Connected"),
    RECONNECTING("Reconnecting..."),
    FAILED("Connection Failed");

    private final String displayName;

    ConnectionStatus(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }

    public boolean isConnected() {
        return this == CONNECTED;
    }

    public boolean isConnecting() {
        return this == CONNECTING || this == RECONNECTING;
    }
}


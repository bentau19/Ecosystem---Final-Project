package com.example.android.network.transport;

/**
 * Represents the current state of the transport layer connection.
 * This is separate from ConnectionStatus and focuses on transport-specific states.
 */
public enum TransportStatus {
    IDLE,              // Not connected, not attempting to connect
    CONNECTING,        // Actively trying to establish connection
    CONNECTED,         // Successfully connected
    RECONNECTING,      // Lost connection, retrying
    DISCONNECTING,     // Gracefully closing connection
    FAILED             // Connection failed permanently
}


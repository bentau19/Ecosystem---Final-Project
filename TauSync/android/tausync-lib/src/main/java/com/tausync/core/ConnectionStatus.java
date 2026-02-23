package com.tausync.core;

/**
 * Connection status enumeration.
 * Defines the possible states of a connection.
 */
public enum ConnectionStatus {
    /**
     * Not connected to any device.
     */
    Disconnected,
    
    /**
     * Scanning for available devices.
     */
    Scanning,
    
    /**
     * Currently establishing a connection.
     */
    Connecting,
    
    /**
     * Successfully connected to a device.
     */
    Connected,
    
    /**
     * An error occurred during connection or communication.
     */
    Error
}

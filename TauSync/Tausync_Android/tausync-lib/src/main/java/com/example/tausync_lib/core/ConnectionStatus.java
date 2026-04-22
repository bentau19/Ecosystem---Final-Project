package com.example.tausync_lib.core;

/**
 * Possible states of a TauSync connection.
 */
public enum ConnectionStatus {
    Disconnected,
    Scanning,
    Connecting,
    Connected,
    Error
}

package com.example.android.domain.enums;

/**
 * Phases of the first-time Bluetooth discovery + pairing flow, surfaced by
 * {@code MainViewModel} so the UI can render scanning/pairing progress and react to results.
 */
public enum DiscoveryStatus {
    /** No discovery in progress. */
    IDLE,
    /** Scanning for the PC's BLE beacon. */
    SCANNING,
    /** A PC was found; awaiting the user's confirmation to pair. */
    PC_FOUND,
    /** Bonding with the chosen PC. */
    PAIRING,
    /** Bonded successfully; the MAC is saved and the connection can start. */
    PAIRED,
    /** Discovery or pairing failed (see the error message). */
    FAILED
}

package com.example.android.domain.enums;

/**
 * Represents the lifecycle states of the webcam streaming session (Android → PC).
 *
 * Transitions:
 *   IDLE → STREAMING   (user taps Start, handshake sent and frames flowing)
 *   STREAMING → STOPPED (user taps Stop or connection drops gracefully)
 *   (any state) → FAILED (network error or I/O failure)
 */
public enum WebcamStatus {

    /** No active webcam session. Default / reset state. */
    IDLE,

    /** Frames are currently being streamed to the PC. */
    STREAMING,

    /** Stream ended gracefully. */
    STOPPED,

    /** Stream failed due to a network error or I/O failure. */
    FAILED
}

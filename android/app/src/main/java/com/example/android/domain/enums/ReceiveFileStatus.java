package com.example.android.domain.enums;

/**
 * Represents the lifecycle states of an incoming file transfer (PC → Android).
 *
 * Transitions:
 *   IDLE → PENDING_APPROVAL  (metadata received, waiting for user)
 *   PENDING_APPROVAL → RECEIVING  (user accepted)
 *   PENDING_APPROVAL → REJECTED   (user rejected)
 *   RECEIVING → COMPLETED         (all bytes received and saved)
 *   RECEIVING → FAILED            (network error or I/O error)
 */
public enum ReceiveFileStatus {

    /** No active transfer. Default / reset state. */
    IDLE,

    /** Metadata received from PC, waiting for user's Accept / Reject decision. */
    PENDING_APPROVAL,

    /** User accepted — bytes are currently streaming in. */
    RECEIVING,

    /** Transfer finished successfully. File saved to Downloads. */
    COMPLETED,

    /** User rejected the transfer. */
    REJECTED,

    /** Transfer failed due to a network or storage error. */
    FAILED
}

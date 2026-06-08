package com.example.android.domain.enums;

/**
 * Represents the lifecycle states of an outgoing file transfer (Android → PC).
 *
 * Transitions:
 *   IDLE → WAITING_FOR_RESPONSE  (metadata sent to PC, waiting for Accept / Reject)
 *   WAITING_FOR_RESPONSE → SENDING    (PC accepted — streaming bytes)
 *   WAITING_FOR_RESPONSE → REJECTED   (PC rejected)
 *   SENDING → COMPLETED               (all bytes sent successfully)
 *   (any state) → FAILED              (network error, timeout, or I/O error)
 */
public enum SendFileStatus {

    /** No active outgoing transfer. Default / reset state. */
    IDLE,

    /** Metadata sent to PC — waiting for the PC user's Accept / Reject decision. */
    WAITING_FOR_RESPONSE,

    /** PC accepted — file bytes are currently streaming out. */
    SENDING,

    /** All bytes sent successfully. */
    COMPLETED,

    /** PC user rejected the transfer. */
    REJECTED,

    /** Transfer failed due to a network error, timeout, or I/O error. */
    FAILED
}

package com.example.android.domain.enums;

/**
 * Lifecycle state of the backup file-transfer phase (Android → PC).
 *
 * <p>State machine:
 * <pre>
 *   IDLE → SENDING → COMPLETED
 *                  ↘ FAILED
 *   (terminal state) → IDLE  via {@code BackupRepository.resetTransfer()}
 * </pre>
 *
 * <p>SENDING means at least one file is currently being streamed; the repository
 * tracks {@code transferSent} and {@code transferTotal} for the X&nbsp;/&nbsp;Y
 * counter shown in the progress notification.
 */
public enum BackupTransferStatus {

    /** No active backup transfer. Default / reset state. */
    IDLE,

    /** Files are currently being sent to the PC one by one. */
    SENDING,

    /** All files sent successfully. */
    COMPLETED,

    /** Transfer failed due to a network error, PC rejection, or I/O error. */
    FAILED
}

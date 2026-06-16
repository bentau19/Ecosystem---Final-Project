package com.example.android.domain.enums;

/**
 * Lifecycle state of the backup file-transfer phase (Android → PC).
 *
 * <p>State machine:
 * <pre>
 *   IDLE → SENDING → COMPLETED
 *                  ↘ FAILED
 *                  ↘ STOPPED          (user tapped Stop in notification)
 *                  ↘ CANCELED_BY_PC   (PC rejected before any file was sent)
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

    /** Transfer suspended by the user; can be resumed. */
    PAUSED,

    /** All files sent successfully. */
    COMPLETED,

    /** Transfer was intentionally stopped by the user via the phone notification. */
    STOPPED,

    /**
     * PC explicitly rejected the session before any file was sent — the user
     * dismissed the destination folder-picker dialog on the PC side.
     *
     * <p>Distinct from {@link #STOPPED} (user-initiated mid-transfer stop) so that
     * {@code BackupFragment} can stay on-screen with a Toast instead of navigating
     * back to {@code ActionsFragment}.
     */
    CANCELED_BY_PC,

    /** Transfer failed due to a network error or I/O error. */
    FAILED
}

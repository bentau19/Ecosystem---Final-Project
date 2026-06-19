package com.example.android.domain.enums;

/**
 * Lifecycle state of the local file-scanning phase of a backup operation.
 *
 * <p>State machine:
 * <pre>
 *   IDLE → SCANNING → READY
 *                   ↘ EMPTY   (scan completed, zero files found)
 *                   ↘ FAILED
 *   (any terminal state) → IDLE  (via BackupRepository.reset())
 * </pre>
 *
 * <p>READY means {@code BackupRepository.getScannedFiles()} contains a populated,
 * sorted list ready to be sent to the desktop as the backup manifest.
 */
public enum BackupScanStatus {

    /** No scan has been started or the repository has been reset. */
    IDLE,

    /** A scan is currently running on a background thread. */
    SCANNING,

    /** Scan completed successfully — file list is available. */
    READY,

    /** Scan completed but found zero files to back up (empty device or empty folder). */
    EMPTY,

    /** Scan failed due to an I/O error or missing permissions. */
    FAILED
}

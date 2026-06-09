package com.example.android.enums;

/**
 * TauSync meeting-word identifiers for the backup file-transfer protocol.
 *
 * <p>These channels are <b>separate</b> from {@link FileTransferChannels} so that
 * a backup batch transfer never collides with a simultaneous single-file share-sheet
 * transfer on the same TauSync connection.
 *
 * <p>Both Android and the desktop must call {@code tau.connect()} with the exact same
 * string for each channel.  Define channel names here once and consume from both sides.
 *
 * <p>Protocol per file (Android → PC):
 * <ol>
 *   <li>Android sends JSON metadata on {@link #METADATA_ANDROID_TO_PC}.</li>
 *   <li>PC responds ACCEPTED / REJECTED on {@link #RESPONSE_FROM_PC}.</li>
 *   <li>If accepted: Android streams raw bytes on {@link #DATA_ANDROID_TO_PC}.</li>
 * </ol>
 */
public enum BackupChannels {

    /** Android sends per-file JSON metadata to PC: {@code {file_name, file_size, modified_at}}. */
    METADATA_ANDROID_TO_PC("backup_meta_android"),

    /** Android streams raw file bytes to PC (after PC has sent ACCEPTED). */
    DATA_ANDROID_TO_PC("backup_data_android"),

    /** PC writes {@code "ACCEPTED"} or {@code "REJECTED"} after receiving metadata. */
    RESPONSE_FROM_PC("backup_response_pc");

    private final String value;

    BackupChannels(String value) {
        this.value = value;
    }

    /** @return The exact meeting-word string passed to {@code TauSync.connect()}. */
    public String getValue() {
        return value;
    }
}

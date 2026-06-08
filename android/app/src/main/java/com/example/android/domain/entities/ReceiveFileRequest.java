package com.example.android.domain.entities;

/**
 * Represents an incoming file transfer request initiated by the remote PC.
 *
 * This entity is part of the Domain layer — it carries only raw data
 * and has zero knowledge of Android APIs, networking, or UI.
 *
 * Lifecycle:
 *   PC sends metadata → FileMetadataChannelHandler parses JSON
 *   → constructs this object → pushes it into ReceiveFileRepository
 *   → LiveData notifies ViewModel → UI shows approval dialog.
 */
public class ReceiveFileRequest {

    private final String fileName;
    private final long fileSizeBytes;

    public ReceiveFileRequest(String fileName, long fileSizeBytes) {
        this.fileName = fileName;
        this.fileSizeBytes = fileSizeBytes;
    }

    public String getFileName() {
        return fileName;
    }

    public long getFileSizeBytes() {
        return fileSizeBytes;
    }

    /**
     * Returns a human-readable file size string (e.g. "3.2 MB", "512 KB").
     * Used directly by the UI dialog — no formatting logic leaks into the View.
     */
    public String getFormattedSize() {
        if (fileSizeBytes >= 1024 * 1024) {
            return String.format("%.1f MB", fileSizeBytes / (1024.0 * 1024.0));
        } else if (fileSizeBytes >= 1024) {
            return String.format("%.1f KB", fileSizeBytes / 1024.0);
        } else {
            return fileSizeBytes + " B";
        }
    }
}

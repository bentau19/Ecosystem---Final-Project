package com.example.android.domain.entities;

/**
 * Represents an incoming file transfer request initiated by the remote PC.
 * <p>
 * This entity is part of the Domain layer — it carries only raw data
 * and has zero knowledge of Android APIs, networking, or UI.
 * <p>
 * Lifecycle:
 * PC sends metadata → FileMetadataChannelHandler parses JSON
 * → constructs this object → pushes it into ReceiveFileRepository
 * → LiveData notifies ViewModel → UI shows approval dialog.
 */
public record ReceiveFileRequest(String fileName, long fileSizeBytes) {

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

package com.example.android.domain.entities;

import androidx.annotation.NonNull;

import com.example.android.data.datasource.BackupDataSource;

import java.io.InputStream;

/**
 * Describes a single candidate file for a backup operation.
 *
 * <p>This entity is part of the Domain layer — it carries only raw data and has
 * zero knowledge of Android APIs, networking, or UI.
 *
 * <p>Two audiences consume this object:
 * <ol>
 *   <li><b>Desktop PC</b> — {@code displayPath}, {@code sizeBytes}, and {@code mtimeMs}
 *       are serialised as JSON and sent over the TauSync backup-manifest channel so
 *       the PC can populate its {@code BackupFileDTO} and show the review dialog.</li>
 *   <li><b>Android transfer phase</b> — {@code sourceUri} is an opaque URI string
 *       (e.g. a {@code content://} URI) that {@code BackupDataSource} uses to open
 *       an {@link InputStream} when streaming the file to the PC.
 *       It is kept locally and never sent to the desktop.</li>
 * </ol>
 *
 * <p>{@code sourceUri} is stored as a plain {@code String} (not {@code android.net.Uri})
 * so this class remains framework-free and unit-testable without an emulator.
 *
 * @param displayPath Human-readable file path shown in the desktop review dialog and used as the
 *                    primary key by {@code BackupFileDTO}.
 *
 *                    <ul>
 *                    <li>For <b>MediaStore</b> entries: the absolute filesystem path
 *                    (e.g. {@code /storage/emulated/0/DCIM/Camera/photo.jpg}).</li>
 *                    <li>For <b>SAF</b> entries: a reconstructed display path
 *                    (e.g. {@code /DCIM/Camera/photo.jpg}) built by joining ancestor
 *                    {@code DocumentFile.getName()} values during the recursive walk.</li>
 *                    </ul>
 * @param sizeBytes   Total file size in bytes.
 * @param mtimeMs     Last-modified time as Unix epoch <em>milliseconds</em>.
 *
 *                    <p>Note: {@code MediaStore.MediaColumns.DATE_MODIFIED} is stored in <b>seconds</b>
 *                    and must be multiplied by 1000 before being placed here. The desktop
 *                    {@code BackupReviewDialog} divides by 1000 when formatting the date label.
 * @param sourceUri   Android URI string used by {@link BackupDataSource}
 *                    to open an {@link InputStream} during the file-transfer phase.
 *
 *                    <ul>
 *                    <li>For <b>MediaStore</b> entries: a {@code content://media/external/…} URI.</li>
 *                    <li>For <b>SAF</b> entries: the {@code DocumentFile.getUri().toString()} value.</li>
 *                    </ul>
 *
 *                    <p>Never serialised or sent to the desktop.
 * @param relPath     Optional relative path of this file within its chosen root folder.
 *
 *                    <p>Populated only for {@code MODE_FOLDER} backups (both the SAF and File-API
 *                    scan paths). Sent to the desktop inside the per-slot JSON header as
 *                    {@code "rel_path"} so the PC can reconstruct the original folder structure
 *                    under the user-chosen destination directory.
 *
 *                    <p>Examples:
 *                    <ul>
 *                    <li>Root = {@code /Downloads}, file = {@code /Downloads/work/report.pdf}
 *                    → {@code relPath = "work/report.pdf"}</li>
 *                    <li>File directly in root → {@code relPath = "report.pdf"}</li>
 *                    </ul>
 *
 *                    <p>{@code null} for {@code MODE_ALL_MEDIA} entries — the desktop saves those
 *                    files flat and falls back to {@code meta["name"]} (the bare filename).
 */
public record BackupFileEntry(String displayPath, String uuid, long sizeBytes, long mtimeMs,
                              String sourceUri, String relPath) {

    /**
     * Full constructor used by folder-scan paths that carry relative-path info.
     *
     * @param displayPath Human-readable absolute/reconstructed path.
     * @param uuid        unique uuid to identify file
     * @param sizeBytes   File size in bytes.
     * @param mtimeMs     Last-modified time in milliseconds since epoch.
     * @param sourceUri   Android URI string for opening an InputStream.
     * @param relPath     Relative path within the chosen root folder, or {@code null}.
     */
    public BackupFileEntry {
    }

    /**
     * Convenience constructor for scan paths that do not carry relative-path info
     * (e.g. {@code scanAllMedia}, {@code queryMediaStore}).
     * Sets {@code relPath} to {@code null}.
     */
    public BackupFileEntry(String displayPath, long sizeBytes, long mtimeMs, String sourceUri, String uuid) {
        this(displayPath, uuid, sizeBytes, mtimeMs, sourceUri, null);
    }

    /**
     * Returns the relative path of this file within its chosen root folder, or
     * {@code null} when the entry came from an all-media scan (no folder context).
     */
    @Override
    public String relPath() {
        return relPath;
    }

    @NonNull
    @Override
    public String toString() {
        return "BackupFileEntry{path='" + displayPath + "', size=" + sizeBytes
                + ", mtime=" + mtimeMs
                + (relPath != null ? ", relPath='" + relPath + "'" : "")
                + '}';
    }
}

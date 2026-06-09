package com.example.android.domain.entities;

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
 *       an {@link java.io.InputStream} when streaming the file to the PC.
 *       It is kept locally and never sent to the desktop.</li>
 * </ol>
 *
 * <p>{@code sourceUri} is stored as a plain {@code String} (not {@code android.net.Uri})
 * so this class remains framework-free and unit-testable without an emulator.
 */
public class BackupFileEntry {

    /**
     * Human-readable file path shown in the desktop review dialog and used as the
     * primary key by {@code BackupFileDTO}.
     *
     * <ul>
     *   <li>For <b>MediaStore</b> entries: the absolute filesystem path
     *       (e.g. {@code /storage/emulated/0/DCIM/Camera/photo.jpg}).</li>
     *   <li>For <b>SAF</b> entries: a reconstructed display path
     *       (e.g. {@code /DCIM/Camera/photo.jpg}) built by joining ancestor
     *       {@code DocumentFile.getName()} values during the recursive walk.</li>
     * </ul>
     */
    private final String displayPath;

    /** Total file size in bytes. */
    private final long sizeBytes;

    /**
     * Last-modified time as Unix epoch <em>milliseconds</em>.
     *
     * <p>Note: {@code MediaStore.MediaColumns.DATE_MODIFIED} is stored in <b>seconds</b>
     * and must be multiplied by 1000 before being placed here. The desktop
     * {@code BackupReviewDialog} divides by 1000 when formatting the date label.
     */
    private final long mtimeMs;

    /**
     * Android URI string used by {@link com.example.android.data.datasource.BackupDataSource}
     * to open an {@link java.io.InputStream} during the file-transfer phase.
     *
     * <ul>
     *   <li>For <b>MediaStore</b> entries: a {@code content://media/external/…} URI.</li>
     *   <li>For <b>SAF</b> entries: the {@code DocumentFile.getUri().toString()} value.</li>
     * </ul>
     *
     * <p>Never serialised or sent to the desktop.
     */
    private final String sourceUri;

    public BackupFileEntry(String displayPath, long sizeBytes, long mtimeMs, String sourceUri) {
        this.displayPath = displayPath;
        this.sizeBytes   = sizeBytes;
        this.mtimeMs     = mtimeMs;
        this.sourceUri   = sourceUri;
    }

    public String getDisplayPath() { return displayPath; }
    public long   getSizeBytes()   { return sizeBytes;   }
    public long   getMtimeMs()     { return mtimeMs;     }
    public String getSourceUri()   { return sourceUri;   }

    @Override
    public String toString() {
        return "BackupFileEntry{path='" + displayPath + "', size=" + sizeBytes
                + ", mtime=" + mtimeMs + '}';
    }
}

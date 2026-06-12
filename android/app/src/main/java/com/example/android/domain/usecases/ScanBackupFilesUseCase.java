package com.example.android.domain.usecases;

import android.content.Context;
import android.net.Uri;
import android.util.Log;

import java.io.File;

import com.example.android.data.datasource.BackupDataSource;
import com.example.android.domain.entities.BackupFileEntry;

import java.util.List;

/**
 * Orchestrates the local file-scanning phase of a backup operation.
 *
 * <p>Given a mode and an optional folder URI, delegates to {@link BackupDataSource}
 * and reports the result asynchronously via {@link ScanCallback}.
 *
 * <p><b>Must be called from a background thread</b> — the underlying DataSource
 * performs blocking disk/ContentResolver I/O.  The callback is invoked on the
 * same background thread; callers are responsible for posting to the main thread
 * if UI updates are needed (e.g. via {@code LiveData.postValue()}).
 *
 * <p>This class intentionally holds a {@link Context} reference (tolerated pattern
 * in this codebase, matching {@link SendFileUseCase}).  Always pass
 * {@code context.getApplicationContext()} to prevent Activity leaks.
 */
public class ScanBackupFilesUseCase {

    private static final String TAG = "ScanBackupFilesUseCase";

    /** Backup mode constant — backs up every photo and video via MediaStore. */
    public static final String MODE_ALL_MEDIA = "all_media";

    /**
     * Backup mode constant — scans files under a user-selected folder.
     *
     * <p>Accepts two URI schemes in {@link #execute}:
     * <ul>
     *   <li>{@code file://} — returned by {@link
     *       com.example.android.ui.fragments.FolderPickerFragment}; routed to
     *       {@link com.example.android.data.datasource.BackupDataSource#scanFolderByPath}
     *       (File API, no SAF restrictions — Downloads selectable).</li>
     *   <li>{@code content://} — returned by {@link android.content.Intent#ACTION_OPEN_DOCUMENT_TREE}
     *       (SAF fallback); routed to
     *       {@link com.example.android.data.datasource.BackupDataSource#scanFolder}.</li>
     * </ul>
     */
    public static final String MODE_FOLDER = "folder";

    private final BackupDataSource dataSource;
    private final Context context;

    public ScanBackupFilesUseCase(BackupDataSource dataSource, Context context) {
        this.dataSource = dataSource;
        this.context    = context.getApplicationContext();
    }

    /**
     * Callback invoked once the scan completes (or fails).
     * Always called on the background thread that initiated the scan.
     */
    public interface ScanCallback {
        /** Scan completed successfully with a non-null, possibly empty list. */
        void onScanComplete(List<BackupFileEntry> files);

        /** Scan failed — the list is unavailable. */
        void onScanFailed(Exception e);
    }

    /**
     * Executes the scan synchronously on the calling thread.
     *
     * @param mode      One of {@link #MODE_ALL_MEDIA} or {@link #MODE_FOLDER}.
     * @param folderUri SAF tree URI — required when {@code mode == MODE_FOLDER},
     *                  ignored for {@code MODE_ALL_MEDIA}.
     * @param callback  Receives the result or error.
     */
    public void execute(String mode, Uri folderUri, ScanCallback callback) {
        Log.d(TAG, "execute: mode=" + mode
                + (folderUri != null ? ", folderUri=" + folderUri : ""));
        try {
            List<BackupFileEntry> files = scanByMode(mode, folderUri);
            Log.d(TAG, "execute: scan complete — " + files.size() + " files");
            callback.onScanComplete(files);
        } catch (Exception e) {
            Log.e(TAG, "execute: scan failed — " + e.getMessage(), e);
            callback.onScanFailed(e);
        }
    }

    /**
     * Dispatches the scan to the appropriate {@link BackupDataSource} method based on
     * {@code mode} and {@code folderUri}.
     *
     * <p>Routing rules:
     * <ul>
     *   <li>{@link #MODE_FOLDER} + {@code file://} URI — delegated to
     *       {@link BackupDataSource#scanFolderByPath(File)} (File API; no SAF
     *       restrictions — Downloads, root, etc. all work).</li>
     *   <li>{@link #MODE_FOLDER} + {@code content://} URI — SAF fallback via
     *       {@link BackupDataSource#scanFolder(android.content.Context, Uri)}.</li>
     *   <li>{@link #MODE_ALL_MEDIA} — delegated to
     *       {@link BackupDataSource#scanAllMedia(android.content.Context)}.</li>
     * </ul>
     *
     * @param mode      One of {@link #MODE_ALL_MEDIA} or {@link #MODE_FOLDER}.
     * @param folderUri Required when {@code mode == MODE_FOLDER}; ignored otherwise.
     * @return Non-null, possibly empty list of matching files.
     * @throws IllegalArgumentException if {@code mode} is unrecognised or
     *                                  {@code folderUri} is {@code null} for folder mode.
     * @throws Exception                if the underlying DataSource scan fails.
     */
    private List<BackupFileEntry> scanByMode(String mode, Uri folderUri) throws Exception {
        if (MODE_FOLDER.equals(mode)) {
            if (folderUri == null) {
                throw new IllegalArgumentException(
                        "folderUri must not be null when mode is MODE_FOLDER");
            }
            if ("file".equals(folderUri.getScheme())) {
                // file:// URI from the custom FolderPickerFragment — use File API.
                // This path has no SAF restrictions (Downloads, root, etc. all work).
                File folder = new File(folderUri.getPath());
                Log.d(TAG, "scanByMode: MODE_FOLDER via File API — " + folder.getAbsolutePath());
                return dataSource.scanFolderByPath(folder);
            } else {
                // content:// SAF URI from ACTION_OPEN_DOCUMENT_TREE fallback.
                return dataSource.scanFolder(context, folderUri);
            }
        } else if (MODE_ALL_MEDIA.equals(mode)) {
            return dataSource.scanAllMedia(context);
        } else {
            throw new IllegalArgumentException("Unknown backup mode: " + mode);
        }
    }
}

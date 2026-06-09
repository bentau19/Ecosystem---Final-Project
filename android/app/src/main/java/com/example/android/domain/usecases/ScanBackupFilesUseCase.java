package com.example.android.domain.usecases;

import android.content.Context;
import android.net.Uri;
import android.util.Log;

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

    /** Backup mode constant — scans files under a user-selected SAF folder tree. */
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
            List<BackupFileEntry> files;

            if (MODE_FOLDER.equals(mode)) {
                if (folderUri == null) {
                    throw new IllegalArgumentException(
                            "folderUri must not be null when mode is MODE_FOLDER");
                }
                files = dataSource.scanFolder(context, folderUri);

            } else if (MODE_ALL_MEDIA.equals(mode)) {
                files = dataSource.scanAllMedia(context);

            } else {
                throw new IllegalArgumentException("Unknown backup mode: " + mode);
            }

            Log.d(TAG, "execute: scan complete — " + files.size() + " files");
            callback.onScanComplete(files);

        } catch (Exception e) {
            Log.e(TAG, "execute: scan failed — " + e.getMessage(), e);
            callback.onScanFailed(e);
        }
    }
}

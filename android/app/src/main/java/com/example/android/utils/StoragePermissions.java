package com.example.android.utils;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.Settings;
import android.util.Log;

import androidx.fragment.app.Fragment;

/**
 * Helpers for the "All files access" special app access
 * ({@code MANAGE_EXTERNAL_STORAGE}).
 *
 * <p>The permission is declared in the manifest but — unlike a runtime
 * permission — it can only be granted by the user on a system settings screen;
 * it never appears in the normal per-app permission list. Two features depend
 * on it:
 *
 * <ul>
 *   <li><b>Backup</b> — optional. Without it the scan still runs, just without
 *       private app media directories.</li>
 *   <li><b>Virtual Drive</b> — required for writes. The data source uses the raw
 *       {@code java.io.File} API, so with {@code targetSdk} on scoped storage
 *       every create/write/delete outside app-owned directories fails with
 *       {@code EPERM} ("Operation not permitted") until this is granted.</li>
 * </ul>
 */
public final class StoragePermissions {

    private static final String TAG = "StoragePermissions";

    private StoragePermissions() {
    }

    /**
     * Whether the app can read and write shared storage through the File API.
     *
     * @return {@code true} on API 29 and below (the File API is unrestricted
     *         there), otherwise whether All files access has been granted.
     */
    public static boolean hasAllFilesAccess() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            return true;
        }
        return Environment.isExternalStorageManager();
    }

    /**
     * Opens the system All files access screen for this app.
     *
     * <p>Some OEMs do not expose the per-app screen, so a failure to resolve it
     * falls back to the generic device-wide list.
     *
     * @param fragment    the caller; its {@code onActivityResult} receives the return trip.
     * @param requestCode request code passed to {@code startActivityForResult}.
     */
    public static void openSettings(Fragment fragment, int requestCode) {
        try {
            Intent intent = new Intent(
                    Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:" + fragment.requireContext().getPackageName()));
            fragment.startActivityForResult(intent, requestCode);
        } catch (Exception e) {
            Log.w(TAG, "Per-app all-files screen unavailable, opening generic screen");
            fragment.startActivityForResult(
                    new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION),
                    requestCode);
        }
    }
}

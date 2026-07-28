package com.example.android.utils;
import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.Settings;
import android.util.Log;

import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;

/**
 * Everything the app needs to read the user's storage: the runtime permissions for photos and
 * videos, and the separate "All files access" special app access.
 *
 * <p>Android renamed and split the media permissions twice, so the correct set depends entirely on
 * the API level. Keeping the rules here means the connect flow (which asks for them up front) and
 * the backup flow (which needs them to scan) can never disagree about what "storage access" means.
 *
 * <p>Full-filesystem access ({@code MANAGE_EXTERNAL_STORAGE}, needed to reach app-private folders
 * MediaStore never indexes, and to write through the raw {@code java.io.File} API at all) is <b>not</b>
 * a runtime permission — it is declared in the manifest but can only be granted by the user on a
 * system settings screen, and never appears in the normal per-app permission list. It is handled by
 * {@link #hasAllFilesAccess()} and {@link #openSettings(Fragment, int)}; callers request it at the
 * point it is actually needed, with an explanation. Two features depend on it:
 *
 * <ul>
 *   <li><b>Backup</b> — optional. Without it the scan still runs, just without private app media
 *       directories.</li>
 *   <li><b>Virtual Drive</b> — required, for reads as much as writes. The data source uses the raw
 *       {@code java.io.File} API, so under scoped storage every create/write/delete outside
 *       app-owned directories fails with {@code EPERM} ("Operation not permitted"), and
 *       {@code listFiles()} silently returns only app-owned files plus media covered by the
 *       granted {@code READ_MEDIA_*} permissions — a drive that browses but shows almost
 *       nothing. Both paths refuse up front until this is granted.</li>
 * </ul>
 */
public final class StoragePermissions {

    private static final String TAG = "StoragePermissions";

    private StoragePermissions() {
    }

    /**
     * The permissions to request on this device:
     * <ul>
     *   <li>API 34+: images + videos, plus the "selected photos only" permission that lets the user
     *       grant access to a subset instead of the whole library.</li>
     *   <li>API 33: images + videos.</li>
     *   <li>API 24–32: the single pre-split {@code READ_EXTERNAL_STORAGE}.</li>
     * </ul>
     */
    public static String[] required() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            return new String[]{
                    Manifest.permission.READ_MEDIA_IMAGES,
                    Manifest.permission.READ_MEDIA_VIDEO,
                    Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED
            };
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            return new String[]{
                    Manifest.permission.READ_MEDIA_IMAGES,
                    Manifest.permission.READ_MEDIA_VIDEO
            };
        }
        return new String[]{Manifest.permission.READ_EXTERNAL_STORAGE};
    }

    /**
     * True when the app can read media. On API 34+ a partial grant ("selected photos") counts:
     * the scan simply proceeds with whatever is accessible, so demanding the full grant would
     * refuse a user who deliberately chose to share less.
     */
    public static boolean areGranted(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            return isGranted(context, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)
                    || (isGranted(context, Manifest.permission.READ_MEDIA_IMAGES)
                    && isGranted(context, Manifest.permission.READ_MEDIA_VIDEO));
        }
        for (String permission : required()) {
            if (!isGranted(context, permission)) {
                return false;
            }
        }
        return true;
    }

    private static boolean isGranted(Context context, String permission) {
        return ContextCompat.checkSelfPermission(context, permission)
                == PackageManager.PERMISSION_GRANTED;
    }

    // ── All files access (MANAGE_EXTERNAL_STORAGE) ───────────────────────────

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

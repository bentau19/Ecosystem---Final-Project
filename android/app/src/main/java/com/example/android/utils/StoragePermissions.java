package com.example.android.utils;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;

import androidx.core.content.ContextCompat;

/**
 * The runtime permissions needed to read the user's photos and videos, and the rules for deciding
 * whether they are held.
 *
 * <p>Android renamed and split this permission twice, so the correct set depends entirely on the
 * API level. Keeping the rules here means the connect flow (which asks for them up front) and the
 * backup flow (which needs them to scan) can never disagree about what "storage access" means.
 *
 * <p>Note this covers only the *runtime* permissions. Full-filesystem access
 * ({@code MANAGE_EXTERNAL_STORAGE}, needed to reach app-private folders MediaStore never indexes)
 * is not a runtime permission — it is granted through a system settings screen, which
 * {@code BackupFragment} requests separately with an explanation, at the point it is actually
 * needed.
 */
public final class StoragePermissions {

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
}

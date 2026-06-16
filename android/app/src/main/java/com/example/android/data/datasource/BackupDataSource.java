package com.example.android.data.datasource;

import android.Manifest;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.Context;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.storage.StorageManager;
import android.os.storage.StorageVolume;
import android.provider.MediaStore;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.documentfile.provider.DocumentFile;

import com.example.android.domain.entities.BackupFileEntry;

import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Platform I/O for backup file enumeration.
 *
 * <p>Two scanning strategies produce the same {@link BackupFileEntry} shape:
 * <ol>
 *   <li>{@link #scanFolder} — recursively walks a user-granted SAF tree URI.</li>
 *   <li>{@link #scanAllMedia} — returns all images and videos: walks the full filesystem
 *       when {@code MANAGE_EXTERNAL_STORAGE} is held, otherwise queries {@code MediaStore}.</li>
 * </ol>
 *
 * <p>Both methods are <b>synchronous</b> and may block for several seconds on large
 * libraries. Always call from a background thread — never from the main thread.
 *
 * <p>Threading note: this class is stateless; a single instance can be shared across threads.
 */
public class BackupDataSource {

    private static final String TAG = "BackupDataSource";

    // ── File-path folder scan (no SAF — used by custom FolderPickerFragment) ──

    /**
     * Recursively enumerates every file under {@code folder} using the {@link File} API.
     *
     * <p>This method has <b>no SAF restrictions</b> — it can scan Downloads, DCIM root,
     * storage root, and any other directory the app holds permission to read.  It is
     * the companion to {@link #scanFolder} for {@code file://} URIs returned by
     * {@link com.example.android.ui.fragments.FolderPickerFragment}.
     *
     * <p>Includes <b>all file types</b> (not just media), since user-chosen folders
     * like Downloads may contain PDFs, APKs, ZIPs, etc.
     *
     * <p>Results are sorted alphabetically by {@code displayPath}.
     *
     * @param folder The directory to scan.  Must be readable by the process.
     * @return Sorted list of {@link BackupFileEntry} objects; empty if the folder
     * is empty or unreadable.
     */

    public List<BackupFileEntry> scanFolderByPath(@NonNull File folder) {
        Log.d(TAG, "scanFolderByPath: starting recursive scan of " + folder.getAbsolutePath());
        List<BackupFileEntry> results = new ArrayList<>();

        if (!folder.isDirectory() || !folder.canRead()) {
            Log.w(TAG, "scanFolderByPath: not a readable directory — " + folder);
            return results;
        }

        walkAllFilesTree(folder, folder, results);

        results.sort(Comparator.comparing(BackupFileEntry::displayPath));
        Log.d(TAG, "scanFolderByPath: found " + results.size() + " files");
        return results;
    }

    /**
     * Recursively walks {@code dir} using {@link File} API and appends <b>every</b>
     * file it finds to {@code out} — no extension filter.
     *
     * <p>Used for user-selected folder scans where the caller chose a specific
     * directory and expects all its contents, not just media.
     *
     * @param dir        Current directory being walked.
     * @param rootFolder The top-level folder the user originally selected.
     *                   Used to compute the relative path of each file so the
     *                   desktop can reconstruct the original folder structure.
     * @param out        Accumulator list.
     */
    private void walkAllFilesTree(@NonNull File dir,
                                  @NonNull File rootFolder,
                                  @NonNull List<BackupFileEntry> out) {
        if (!dir.isDirectory() || !dir.canRead()) return;

        File[] children = dir.listFiles();
        if (children == null) return;

        final String rootAbs = rootFolder.getAbsolutePath();

        for (File child : children) {
            if (child.isDirectory()) {
                walkAllFilesTree(child, rootFolder, out);
            } else if (child.isFile()) {
                String absPath = child.getAbsolutePath();
                long sizeBytes = child.length();
                long mtimeMs = child.lastModified();
                String sourceUri = android.net.Uri.fromFile(child).toString();

                // Compute relative path within the chosen root folder so the desktop
                // can mirror the directory structure under its destination.
                // e.g. root="/Downloads", file="/Downloads/work/report.pdf"
                //      → relPath = "work/report.pdf"
                String relPath = absPath.startsWith(rootAbs + "/")
                        ? absPath.substring(rootAbs.length() + 1)
                        : child.getName(); // fallback: just the filename

                out.add(new BackupFileEntry(absPath, java.util.UUID.randomUUID().toString(),
                        sizeBytes, mtimeMs, sourceUri, relPath));
            }
        }
    }

    // ── SAF folder scan ───────────────────────────────────────────────────────

    /**
     * Recursively enumerates every file under {@code treeUri} using the Storage
     * Access Framework.
     *
     * <p>The {@code displayPath} of each entry is reconstructed by joining the
     * {@link DocumentFile#getName()} values of all ancestors, producing a
     * human-readable path like {@code /DCIM/Camera/photo.jpg} that the desktop
     * review dialog can display.
     *
     * <p>Entries are sorted alphabetically by {@code displayPath}.
     *
     * @param context Application context — used for {@code DocumentFile} resolution.
     * @param treeUri A persistable tree URI obtained via
     *                {@link android.content.Intent#ACTION_OPEN_DOCUMENT_TREE}.
     * @return Sorted list of {@link BackupFileEntry} objects; empty if the folder
     * is empty or the URI is unreadable.
     */
    public List<BackupFileEntry> scanFolder(Context context, Uri treeUri) {
        Log.d(TAG, "scanFolder: starting recursive scan of " + treeUri);
        List<BackupFileEntry> results = new ArrayList<>();

        DocumentFile root = DocumentFile.fromTreeUri(context, treeUri);
        if (root == null || !root.isDirectory()) {
            Log.w(TAG, "scanFolder: treeUri is not a readable directory — " + treeUri);
            return results;
        }

        // Use the root folder name as the display root (e.g. "Camera" or "DCIM")
        String rootDisplayName = root.getName();
        String rootPrefix = (rootDisplayName != null && !rootDisplayName.isEmpty())
                ? "/" + rootDisplayName
                : "";

        walkDocumentTree(context, root, rootPrefix, "", results);

        results.sort(Comparator.comparing(BackupFileEntry::displayPath));
        Log.d(TAG, "scanFolder: found " + results.size() + " files");
        return results;
    }

    /**
     * Recursively visits {@code dir} and appends every file it finds to {@code out}.
     *
     * @param context    Application context.
     * @param dir        Current directory node.
     * @param pathPrefix Display path of this directory (e.g. {@code /DCIM/Camera}).
     * @param relPrefix  Relative path accumulated so far within the root folder
     *                   (e.g. {@code "Camera/2024"}). Empty string at the root level.
     *                   Used to build each file's {@code relPath} so the desktop can
     *                   mirror the directory structure under its destination.
     * @param out        Accumulator list — entries are appended in discovery order.
     */
    private void walkDocumentTree(Context context,
                                  DocumentFile dir,
                                  String pathPrefix,
                                  String relPrefix,
                                  List<BackupFileEntry> out) {
        DocumentFile[] children = dir.listFiles();
        if (children == null) return;

        for (DocumentFile child : children) {
            if (child.isDirectory()) {
                String childName = child.getName();
                if (childName == null) childName = "";
                String childPath = pathPrefix + "/" + childName;
                String childRelPrefix = relPrefix.isEmpty()
                        ? childName
                        : relPrefix + "/" + childName;
                walkDocumentTree(context, child, childPath, childRelPrefix, out);

            } else if (child.isFile()) {
                String fileName = child.getName();
                if (fileName == null || fileName.isEmpty()) continue;

                String displayPath = pathPrefix + "/" + fileName;
                long sizeBytes = child.length();
                long mtimeMs = child.lastModified();  // already in ms
                String sourceUri = child.getUri().toString();

                // relPath mirrors the structure under the root folder so the desktop
                // can recreate subdirectories.
                // e.g. relPrefix="2024", fileName="photo.jpg" → relPath="2024/photo.jpg"
                String relPath = relPrefix.isEmpty()
                        ? fileName
                        : relPrefix + "/" + fileName;

                out.add(new BackupFileEntry(displayPath, java.util.UUID.randomUUID().toString(),
                        sizeBytes, mtimeMs, sourceUri, relPath));
            }
        }
    }

    // ── MediaStore all-media scan ─────────────────────────────────────────────

    /**
     * Returns <b>all images and videos</b> on the device, sorted newest-first.
     *
     * <p><b>Strategy A — full filesystem walk (primary)</b>: when
     * {@link Environment#isExternalStorageManager()} is {@code true} (API 30+),
     * every mounted storage volume is walked directly with {@link #walkFileTree}.
     * This bypasses {@code MediaStore} entirely and finds every media file on the
     * device regardless of indexing status, {@code .nomedia} flags, or whether the
     * file lives in {@code Android/data/}.
     *
     * <p><b>Strategy B — MediaStore (fallback)</b>: when full filesystem access is
     * not available, {@code MediaStore} is queried across all external volumes plus
     * internal storage.  This is limited to Gallery-visible files and misses
     * directories that contain a {@code .nomedia} file.
     *
     * <p>The caller (Fragment) is responsible for requesting the appropriate
     * permissions — {@code READ_MEDIA_IMAGES}/{@code READ_MEDIA_VIDEO} on API 33+,
     * {@code READ_EXTERNAL_STORAGE} on API 24–32 — before invoking this method.
     *
     * @param context Application context.
     * @return List of {@link BackupFileEntry} objects sorted by {@code mtimeMs}
     *         descending; empty if no media found or permissions are absent.
     */
    // ── Media file extension filter ───────────────────────────────────────────

    /**
     * Image and video extensions scanned during the file-tree walk.
     */
    private static final Set<String> MEDIA_EXTENSIONS = new HashSet<>(Arrays.asList(
            // Images
            "jpg", "jpeg", "png", "gif", "bmp", "webp",
            "heic", "heif", "tiff", "tif", "avif", "raw",
            "cr2", "nef", "arw", "dng",
            // Videos
            "mp4", "avi", "mov", "mkv", "3gp", "webm",
            "ts", "m4v", "flv", "wmv", "mts", "m2ts"
    ));

    private static boolean isMediaFile(String name) {
        int dot = name.lastIndexOf('.');
        if (dot < 0) return false;
        return MEDIA_EXTENSIONS.contains(name.substring(dot + 1).toLowerCase(Locale.ROOT));
    }

    // ── scanAllMedia ──────────────────────────────────────────────────────────

    public List<BackupFileEntry> scanAllMedia(Context context) {
        List<BackupFileEntry> results = new ArrayList<>();

        // Determine whether we have enough permission to walk the filesystem directly.
        //
        // • API 30+  — MANAGE_EXTERNAL_STORAGE required; scoped storage otherwise blocks
        //              File API access to most of the filesystem.
        // • API 24–29 — READ_EXTERNAL_STORAGE already grants full filesystem read access;
        //               scoped storage restrictions do not apply on these API levels.
        //
        // In both cases a direct File walk bypasses MediaStore entirely, finding media files
        // in .nomedia directories, unindexed files, and app-private paths that MediaStore
        // never covers.
        final boolean canWalkFilesystem;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            canWalkFilesystem = Environment.isExternalStorageManager();
        } else {
            canWalkFilesystem = context.checkSelfPermission(
                    Manifest.permission.READ_EXTERNAL_STORAGE)
                    == PackageManager.PERMISSION_GRANTED;
        }

        if (canWalkFilesystem) {

            // ── Full filesystem walk ──────────────────────────────────────────
            Set<File> volumeRoots = new LinkedHashSet<>();
            volumeRoots.add(Environment.getExternalStorageDirectory()); // /storage/emulated/0

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                // API 30+: StorageVolume.getDirectory() is available
                StorageManager sm = (StorageManager)
                        context.getSystemService(Context.STORAGE_SERVICE);
                if (sm != null) {
                    for (StorageVolume vol : sm.getStorageVolumes()) {
                        File dir = vol.getDirectory();
                        if (dir != null && dir.canRead()) volumeRoots.add(dir);
                    }
                }
            } else {
                // API 24–29: StorageVolume.getDirectory() not available — derive volume roots
                // from getExternalFilesDirs(). Each path is of the form:
                //   /storage/<id>/Android/data/<pkg>/files
                // The volume root is 4 levels above the app-specific dir.
                File[] appDirs = context.getExternalFilesDirs(null);
                if (appDirs != null) {
                    for (File appDir : appDirs) {
                        File volumeRoot = volumeRootFromAppDir(appDir);
                        if (volumeRoot != null) volumeRoots.add(volumeRoot);
                    }
                }
            }

            for (File root : volumeRoots) {
                int before = results.size();
                walkFileTree(root, results);
                Log.d(TAG, "scanAllMedia: walked " + root.getAbsolutePath()
                        + " → " + (results.size() - before) + " files");
            }

        } else {

            // ── MediaStore fallback ───────────────────────────────────────────
            // No full filesystem access — query MediaStore.
            // Misses .nomedia dirs and unindexed files, but covers the Gallery-visible set.
            Log.d(TAG, "scanAllMedia: no filesystem permission — querying MediaStore");

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                // On API 29+, EXTERNAL_CONTENT_URI misses additional volumes on many OEM ROMs.
                // Iterating getExternalVolumeNames() hits every mounted volume explicitly.
                Set<String> volumes = MediaStore.getExternalVolumeNames(context);
                Log.d(TAG, "scanAllMedia: found " + volumes.size()
                        + " external volumes: " + volumes);
                for (String vol : volumes) {
                    queryMediaStore(context,
                            MediaStore.Images.Media.getContentUri(vol),
                            "images[" + vol + "]", results);
                    queryMediaStore(context,
                            MediaStore.Video.Media.getContentUri(vol),
                            "videos[" + vol + "]", results);
                }
            } else {
                // Pre-Q: single external URI is reliable
                queryMediaStore(context,
                        MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                        "images", results);
                queryMediaStore(context,
                        MediaStore.Video.Media.EXTERNAL_CONTENT_URI,
                        "videos", results);
            }

            // Internal storage (screenshots on some ROMs, system wallpapers, etc.)
            queryMediaStore(context,
                    MediaStore.Images.Media.INTERNAL_CONTENT_URI,
                    "images[internal]", results);
            queryMediaStore(context,
                    MediaStore.Video.Media.INTERNAL_CONTENT_URI,
                    "videos[internal]", results);
        }

        // Newest first — most relevant for incremental backup flows
        results.sort((a, b) -> Long.compare(b.mtimeMs(), a.mtimeMs()));
        Log.d(TAG, "scanAllMedia: total " + results.size() + " files");
        return results;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /**
     * Derives the storage volume root from an app-specific external directory path.
     *
     * <p>{@link Context#getExternalFilesDirs} returns paths like
     * {@code /storage/<id>/Android/data/<pkg>/files} — the volume root is 4 levels up.
     * Used on API 24–29 where {@link StorageVolume#getDirectory()} is not yet available.
     *
     * @param appDir e.g. {@code /storage/XXXX-XXXX/Android/data/com.example.android/files}
     * @return Volume root (e.g. {@code /storage/XXXX-XXXX}), or {@code null} if it cannot
     * be derived or is not readable.
     */
    private static File volumeRootFromAppDir(File appDir) {
        if (appDir == null) return null;
        File f = appDir;
        for (int i = 0; i < 4; i++) {
            f = f.getParentFile();
            if (f == null) return null;
        }
        return f.canRead() ? f : null;
    }

    // ── File-tree walk (used when MANAGE_EXTERNAL_STORAGE is granted) ─────────

    /**
     * Recursively walks {@code dir} using {@link File} API and appends every media
     * file it finds to {@code out}.
     *
     * <p>Only called when the process has full filesystem read permission:
     * {@link Environment#isExternalStorageManager()} on API 30+, or
     * {@link Manifest.permission#READ_EXTERNAL_STORAGE} on API 24–29. Callers pass a
     * volume root such as {@link Environment#getExternalStorageDirectory()} or a root
     * derived from {@link Context#getExternalFilesDirs}.
     * Filters by {@link #MEDIA_EXTENSIONS} so only image and video files are included.
     *
     * <p>Uses the absolute path as {@code displayPath} and a {@code file://} URI as
     * {@code sourceUri}. {@link android.content.ContentResolver#openInputStream}
     * accepts {@code file://} URIs when the app holds full filesystem access.
     *
     * @param dir Current directory — silently skipped if {@code null}, not a directory,
     *            or not readable.
     * @param out Accumulator list.
     */
    private void walkFileTree(File dir, List<BackupFileEntry> out) {
        if (dir == null || !dir.isDirectory() || !dir.canRead()) return;

        File[] children = dir.listFiles();
        if (children == null) return;

        for (File child : children) {
            if (child.isDirectory()) {
                walkFileTree(child, out);
            } else if (child.isFile() && isMediaFile(child.getName())) {
                String absPath = child.getAbsolutePath();
                long sizeBytes = child.length();
                long mtimeMs = child.lastModified();  // already in ms
                // file:// URI — readable via ContentResolver.openInputStream() when
                // MANAGE_EXTERNAL_STORAGE is held, and via new FileInputStream() directly.
                String sourceUri = android.net.Uri.fromFile(child).toString();

                out.add(new BackupFileEntry(absPath, sizeBytes, mtimeMs, sourceUri, java.util.UUID.randomUUID().toString()));
            }
        }
    }

    // ── Post-transfer cleanup ─────────────────────────────────────────────────

    /**
     * Deletes the on-device source file referenced by {@code entry.getSourceUri()}.
     *
     * <p>Called by {@link com.example.android.domain.usecases.BackupTransferUseCase}
     * only after the PC has confirmed it received and saved the file successfully
     * (i.e. {@link com.example.android.enums.BackupFileResult#SUCCESS} on the
     * corresponding {@code backup_file_result_*} channel) and the user enabled
     * "Delete originals after backup".
     *
     * <p>Handles both URI shapes produced by the scan paths:
     * <ul>
     *   <li>{@code content://} — MediaStore entries ({@link #queryMediaStore}) and SAF
     *       document URIs ({@link #walkDocumentTree}). Deleted via
     *       {@link ContentResolver#delete(Uri, String, String[])}, which Android routes
     *       to the owning provider's {@code delete()} (MediaStore or DocumentsProvider)
     *       — both support single-document deletion this way.</li>
     *   <li>{@code file://} — entries from {@link #walkFileTree} / {@link #walkAllFilesTree}.
     *       Deleted directly via {@link File#delete()}.</li>
     * </ul>
     *
     * <p>Never throws — any failure is logged and {@code false} is returned so the
     * caller can log a warning without aborting the transfer session.
     *
     * @param context Application context — used for {@link ContentResolver} access.
     * @param entry   The file entry whose {@code sourceUri} should be deleted.
     * @return {@code true} if the file was deleted; {@code false} otherwise.
     */
    public boolean deleteSourceFile(@NonNull Context context, @NonNull BackupFileEntry entry) {
        String sourceUriStr = entry.sourceUri();
        if (sourceUriStr == null || sourceUriStr.isEmpty()) {
            Log.w(TAG, "deleteSourceFile: empty sourceUri for " + entry.displayPath());
            return false;
        }

        try {
            Uri uri = Uri.parse(sourceUriStr);
            String scheme = uri.getScheme();

            if ("file".equals(scheme)) {
                String path = uri.getPath();
                if (path == null) {
                    Log.w(TAG, "deleteSourceFile: file:// URI with null path — " + sourceUriStr);
                    return false;
                }
                boolean deleted = new File(path).delete();
                if (!deleted) {
                    Log.w(TAG, "deleteSourceFile: File.delete() failed for " + path);
                }
                return deleted;
            }

            // content:// — MediaStore or SAF document URI
            ContentResolver resolver = context.getContentResolver();
            int rows = resolver.delete(uri, null, null);
            if (rows <= 0) {
                Log.w(TAG, "deleteSourceFile: ContentResolver.delete() removed 0 rows for "
                        + sourceUriStr);
            }
            return rows > 0;

        } catch (Exception e) {
            Log.e(TAG, "deleteSourceFile: failed for " + entry.displayPath()
                    + " (" + sourceUriStr + ") — " + e.getMessage(), e);
            return false;
        }
    }

    /**
     * Removes now-empty ancestor directories left behind after {@link #deleteSourceFile}
     * removed {@code entry}'s file, walking upward until a non-empty directory or the
     * original backup root is reached.
     *
     * <p>Called by {@link com.example.android.domain.usecases.BackupTransferUseCase}
     * immediately after a successful {@link #deleteSourceFile} call, so no orphan empty
     * folders are left under a folder-mode backup's chosen root.
     *
     * <p><b>Scope</b> — only acts when both are true:
     * <ul>
     *   <li>{@code entry.getRelPath() != null} — i.e. a folder-mode scan
     *       ({@link #scanFolderByPath} / {@link #walkAllFilesTree}) that recorded the
     *       file's path relative to the chosen root. All-media scans
     *       ({@link #scanAllMedia}, {@code relPath == null}) are skipped — walking up
     *       from those could reach shared system directories (e.g. {@code DCIM/Camera}).</li>
     *   <li>{@code entry.getSourceUri()} has scheme {@code "file"} — SAF
     *       ({@code content://}) folder scans ({@link #scanFolder}) are skipped because
     *       {@code DocumentFile.fromSingleUri()} cannot walk to a parent directory.</li>
     * </ul>
     *
     * <p><b>Root boundary</b> — for in-scope entries, {@code displayPath} is the absolute
     * filesystem path and always ends with {@code relPath} (set by
     * {@link #walkAllFilesTree}), so the backup root is recovered by stripping the
     * trailing {@code relPath} (and separator) from {@code displayPath}. The root
     * directory itself is never deleted, and the walk never proceeds above it.
     *
     * <p>Never throws — every outcome is logged via {@code Log.d}/{@code Log.w}.
     *
     * @param entry The just-deleted file's entry.
     */
    public void deleteEmptyParentFolders(@NonNull BackupFileEntry entry) {
        String relPath = entry.relPath();
        if (relPath == null || relPath.isEmpty()) {
            Log.d(TAG, "deleteEmptyParentFolders: skipping (no relPath) — "
                    + entry.displayPath());
            return;
        }

        String sourceUriStr = entry.sourceUri();
        Uri uri;
        try {
            uri = Uri.parse(sourceUriStr);
        } catch (Exception e) {
            Log.w(TAG, "deleteEmptyParentFolders: invalid sourceUri " + sourceUriStr);
            return;
        }
        if (!"file".equals(uri.getScheme())) {
            Log.d(TAG, "deleteEmptyParentFolders: skipping non-file URI — " + sourceUriStr);
            return;
        }

        String displayPath = entry.displayPath();
        if (displayPath == null || !displayPath.endsWith(relPath)) {
            Log.w(TAG, "deleteEmptyParentFolders: displayPath does not end with relPath — "
                    + "displayPath=" + displayPath + ", relPath=" + relPath);
            return;
        }

        String rootPath = displayPath.substring(0, displayPath.length() - relPath.length());
        if (rootPath.endsWith("/")) {
            rootPath = rootPath.substring(0, rootPath.length() - 1);
        }
        if (rootPath.isEmpty()) {
            Log.w(TAG, "deleteEmptyParentFolders: derived empty root for displayPath="
                    + displayPath);
            return;
        }
        File root = new File(rootPath);
        String rootAbs = root.getAbsolutePath();

        File dir = new File(displayPath).getParentFile();
        while (dir != null
                && !dir.getAbsolutePath().equals(rootAbs)
                && dir.getAbsolutePath().startsWith(rootAbs + File.separator)) {

            String[] children = dir.list();
            if (children == null || children.length > 0) {
                // Non-empty (or unreadable) — stop walking up.
                break;
            }

            File parent = dir.getParentFile();
            boolean deleted = dir.delete();
            Log.d(TAG, "deleteEmptyParentFolders: "
                    + (deleted ? "removed empty folder " : "failed to remove ") + dir);
            if (!deleted) break;

            dir = parent;
        }
    }

    /**
     * Executes a single MediaStore query and appends results to {@code out}.
     *
     * <p>{@code DATE_MODIFIED} in MediaStore is stored as Unix <em>seconds</em>.
     * We multiply by 1000 here so {@link BackupFileEntry#mtimeMs()} always
     * holds milliseconds — matching the desktop {@code BackupReviewDialog} which
     * divides by 1000 when formatting the date label.
     *
     * @param context    Application context.
     * @param contentUri e.g. {@link MediaStore.Images.Media#EXTERNAL_CONTENT_URI}
     * @param label      Debug label ("images" or "videos").
     * @param out        Accumulator list.
     */
    private void queryMediaStore(Context context,
                                 Uri contentUri,
                                 String label,
                                 List<BackupFileEntry> out) {
        // DATA is deprecated on API 29+ (scoped storage) and returns null for most files —
        // which caused them to be silently skipped. On API 29+ we use RELATIVE_PATH +
        // DISPLAY_NAME to build a human-readable display path instead.
        // sourceUri always uses the content:// URI so openInputStream() works on all levels.
        String[] projection;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            projection = new String[]{
                    MediaStore.MediaColumns._ID,
                    MediaStore.MediaColumns.RELATIVE_PATH, // e.g. "DCIM/Camera/"
                    MediaStore.MediaColumns.DISPLAY_NAME,  // e.g. "photo.jpg"
                    MediaStore.MediaColumns.SIZE,
                    MediaStore.MediaColumns.DATE_MODIFIED  // seconds since epoch
            };
        } else {
            projection = new String[]{
                    MediaStore.MediaColumns._ID,
                    MediaStore.MediaColumns.DATA,          // absolute path — reliable pre-Q
                    MediaStore.MediaColumns.SIZE,
                    MediaStore.MediaColumns.DATE_MODIFIED
            };
        }

        ContentResolver resolver = context.getContentResolver();

        try (Cursor cursor = resolver.query(contentUri, projection, null, null, null)) {

            if (cursor == null) {
                Log.w(TAG, "queryMediaStore: null cursor for " + label);
                return;
            }

            int idIdx = cursor.getColumnIndex(MediaStore.MediaColumns._ID);
            int sizeIdx = cursor.getColumnIndex(MediaStore.MediaColumns.SIZE);
            int modifiedIdx = cursor.getColumnIndex(MediaStore.MediaColumns.DATE_MODIFIED);
            // API-conditional columns
            int relPathIdx = cursor.getColumnIndex(MediaStore.MediaColumns.RELATIVE_PATH);
            int nameIdx = cursor.getColumnIndex(MediaStore.MediaColumns.DISPLAY_NAME);
            int dataIdx = cursor.getColumnIndex(MediaStore.MediaColumns.DATA);

            int count = 0;
            while (cursor.moveToNext()) {
                long id = cursor.getLong(idIdx);
                long sizeBytes = cursor.getLong(sizeIdx);
                long mtimeMs = cursor.getLong(modifiedIdx) * 1000L; // seconds → ms

                // Build displayPath — guaranteed non-null, never skipped
                String displayPath;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    String relPath = relPathIdx >= 0 ? cursor.getString(relPathIdx) : "";
                    String name = nameIdx >= 0 ? cursor.getString(nameIdx) : String.valueOf(id);
                    if (relPath == null) relPath = "";
                    if (name == null) name = String.valueOf(id);
                    displayPath = ("/" + relPath + name).replace("//", "/");
                } else {
                    String absPath = dataIdx >= 0 ? cursor.getString(dataIdx) : null;
                    displayPath = (absPath != null && !absPath.isEmpty())
                            ? absPath : "/unknown/" + id;
                }

                // Content URI — the only safe InputStream handle on API 29+
                Uri sourceContentUri = ContentUris.withAppendedId(contentUri, id);

                out.add(new BackupFileEntry(displayPath, sizeBytes, mtimeMs,
                        sourceContentUri.toString(),java.util.UUID.randomUUID().toString()));
                count++;
            }
            Log.d(TAG, "queryMediaStore: " + label + " → " + count + " entries");

        } catch (Exception e) {
            Log.e(TAG, "queryMediaStore: failed for " + label + " — " + e.getMessage(), e);
        }
    }
}

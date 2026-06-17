package com.example.android.data.datasource;

import android.os.Environment;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import com.example.android.domain.entities.VDriveEntry;

import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.RandomAccessFile;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

/**
 * File I/O layer for the virtual drive feature.
 *
 * <p>All operations map the virtual path space (rooted at {@code "/"}) 1:1 onto the
 * device's primary external storage ({@link Environment#getExternalStorageDirectory()},
 * i.e. {@code /storage/emulated/0/}).
 *
 * <p><b>Path traversal safety</b>: {@link #resolve} validates that the canonical
 * absolute path of every resolved file starts with the storage root — any attempt
 * to escape via {@code ".."} components throws a {@link SecurityException}.
 *
 * <h3>Metadata cache</h3>
 * <p>Stat and directory-listing results are cached for {@link #CACHE_TTL_MS} milliseconds
 * ({@value #CACHE_TTL_MS} ms = {@value #CACHE_TTL_S} s). This absorbs WinFsp's rapid
 * re-stat storms (Explorer probes every visible entry immediately after a
 * {@code ReadDirectory} call). Cache entries are invalidated on every mutation
 * (create / delete / rename / truncate / finalizeWrite), so stale data is only
 * possible for externally modified files.
 *
 * <p>All methods are <b>synchronous</b> and may block.  Always call from a
 * background thread — never from the main thread.
 *
 * <p>Callers are responsible for holding the appropriate storage permissions
 * before invoking any method:
 * <ul>
 *   <li>API 24–28: {@code READ_EXTERNAL_STORAGE} + {@code WRITE_EXTERNAL_STORAGE}
 *   <li>API 29:    {@code WRITE_EXTERNAL_STORAGE} (still honoured)
 *   <li>API 30+:   {@code MANAGE_EXTERNAL_STORAGE}
 * </ul>
 */
public class VirtualDriveDataSource {

    private static final String TAG = "VirtualDriveDS";

    /**
     * Temp-file suffix used during write sessions to avoid partial writes being visible.
     */
    private static final String TMP_SUFFIX = ".vdtmp";

    /**
     * Cache TTL in milliseconds. Must be short enough that externally modified files
     * (e.g. a photo just taken by the camera) appear within a reasonable delay.
     * 3 s is conservative; the desktop uses 5 s.
     */
    private static final long CACHE_TTL_MS = 3_000L;

    /**
     * Human-readable version of {@link #CACHE_TTL_MS} for log messages.
     */
    private static final int CACHE_TTL_S = 3;

    /**
     * Write-buffer size for temp files. Coalesces small TauSync payload chunks into
     * larger kernel writes, reducing syscall overhead during streaming.
     */
    private static final int WRITE_BUFFER_BYTES = 256 * 1024; // 256 KB

    /**
     * Canonical absolute path of the storage root — used for traversal validation.
     */
    private final String storageRoot;

    // ── Metadata caches ───────────────────────────────────────────────────────

    /**
     * Immutable cache entry: a value paired with its expiry timestamp
     * (milliseconds from {@link System#currentTimeMillis()}).
     */
    private record CacheEntry<T>(T value, long expiryMs) {
    }

    /**
     * Short-TTL stat cache: virtual path → {@link CacheEntry} holding a
     * {@link VDriveEntry} and its expiry timestamp. Absorbs the per-entry stat
     * probes WinFsp issues right after a directory listing.
     * {@link ConcurrentHashMap} is safe for concurrent access from multiple
     * {@code PeerRequestHandler} threads.
     */
    private final ConcurrentHashMap<String, CacheEntry<VDriveEntry>> statCache =
            new ConcurrentHashMap<>();

    /**
     * Short-TTL list cache: virtual path → {@link CacheEntry} holding the full
     * child list and its expiry timestamp. Absorbs Explorer's repeated
     * {@code ReadDirectory} refreshes.
     */
    private final ConcurrentHashMap<String, CacheEntry<List<VDriveEntry>>> listCache =
            new ConcurrentHashMap<>();

    public VirtualDriveDataSource() {
        File root = Environment.getExternalStorageDirectory();
        try {
            storageRoot = root.getCanonicalPath();
        } catch (IOException e) {
            throw new IllegalStateException("Cannot determine external storage root", e);
        }
    }

    // ── Path resolution ───────────────────────────────────────────────────────

    /**
     * Maps a virtual path (e.g. {@code "/DCIM/Camera/photo.jpg"}) to the
     * corresponding {@link File} on disk.
     *
     * @param virtualPath Absolute virtual path from the WinFsp client; {@code "/"} maps
     *                    to the external storage root.
     * @return Resolved {@link File} (may or may not exist).
     * @throws SecurityException if the path escapes the storage root.
     * @throws IOException       if canonical path resolution fails.
     */
    public File resolve(String virtualPath) throws IOException {
        // Strip leading slash so new File(root, "/foo") works correctly.
        String relative = virtualPath.startsWith("/") ? virtualPath.substring(1) : virtualPath;
        File resolved = new File(storageRoot, relative);

        String canonical = resolved.getCanonicalPath();
        if (!canonical.startsWith(storageRoot)) {
            throw new SecurityException(
                    "Virtual path escapes storage root: " + virtualPath);
        }
        return resolved;
    }

    // ── Directory listing ─────────────────────────────────────────────────────

    /**
     * Lists the direct children of the directory at {@code virtualPath}.
     *
     * <p>Results are cached for {@value #CACHE_TTL_S} s. A successful listing also
     * seeds the stat cache for every child so the per-entry stat storm WinFsp issues
     * right after a directory open is served locally without round-trips.
     *
     * @param virtualPath Virtual path of the directory to list.
     * @return List of {@link VDriveEntry} objects; empty if the directory is
     * empty or the path is not a readable directory.
     * @throws IOException       on path resolution failure.
     * @throws SecurityException on traversal attempt.
     */
    public List<VDriveEntry> listDir(String virtualPath) throws IOException {
        // ── Cache check ───────────────────────────────────────────────────────
        CacheEntry<List<VDriveEntry>> hit = listCache.get(virtualPath);
        if (hit != null && hit.expiryMs > System.currentTimeMillis()) {
            Log.v(TAG, "listDir cache hit: " + virtualPath);
            return hit.value;
        }

        // ── Real directory listing ────────────────────────────────────────────
        File dir = resolve(virtualPath);
        List<VDriveEntry> entries = new ArrayList<>();

        if (!dir.isDirectory()) {
            Log.w(TAG, "listDir: not a directory — " + virtualPath);
        } else {
            File[] children = dir.listFiles();
            if (children == null) {
                Log.w(TAG, "listDir: listFiles() returned null for " + virtualPath);
            } else {
                for (File child : children) {
                    entries.add(fileToEntry(child, child.getName()));
                }
            }
        }

        // ── Populate caches ───────────────────────────────────────────────────
        long expiry = System.currentTimeMillis() + CACHE_TTL_MS;
        listCache.put(virtualPath, new CacheEntry<>(entries, expiry));

        // Seed stat cache from listing so the WinFsp stat storm that immediately
        // follows a ReadDirectory call is served from cache — no Android round-trips.
        for (VDriveEntry e : entries) {
            String childPath = childVirtualPath(virtualPath, e.getName());
            statCache.put(childPath, new CacheEntry<>(e, expiry));
        }

        Log.d(TAG, "listDir: " + entries.size() + " entries for " + virtualPath
                + " (cached " + CACHE_TTL_S + "s)");
        return entries;
    }

    // ── Stat ──────────────────────────────────────────────────────────────────

    /**
     * Returns metadata for the file or directory at {@code virtualPath}, or
     * {@code null} if it does not exist.
     *
     * <p>Results are cached for {@value #CACHE_TTL_S} s to absorb WinFsp's repeated
     * {@code stat("/")} refreshes and per-entry probes while browsing.
     *
     * @param virtualPath Virtual path of the target.
     * @return {@link VDriveEntry} if the path exists; {@code null} otherwise.
     * @throws IOException       on path resolution failure.
     * @throws SecurityException on traversal attempt.
     */
    public VDriveEntry stat(String virtualPath) throws IOException {
        // ── Cache check ───────────────────────────────────────────────────────
        CacheEntry<VDriveEntry> hit = statCache.get(virtualPath);
        if (hit != null && hit.expiryMs > System.currentTimeMillis()) {
            Log.v(TAG, "stat cache hit: " + virtualPath);
            return hit.value;
        }

        // ── Real stat ─────────────────────────────────────────────────────────
        File file = resolve(virtualPath);
        if (!file.exists()) {
            return null;
        }
        VDriveEntry entry = fileToEntry(file, file.getName());

        // Cache non-null results only (missing paths are not cached to avoid
        // hiding newly created files from other apps).
        statCache.put(virtualPath,
                new CacheEntry<>(entry, System.currentTimeMillis() + CACHE_TTL_MS));
        return entry;
    }

    // ── Read ──────────────────────────────────────────────────────────────────

    /**
     * Opens a size-limited {@link InputStream} for the byte range
     * [{@code offset}, {@code offset + length}) of the file at
     * {@code virtualPath}.
     *
     * <p>Uses {@link RandomAccessFile#seek} to jump directly to {@code offset}
     * (O(1) via {@code lseek64}). The returned {@link LimitedRandomAccessInputStream}
     * closes the underlying {@code RandomAccessFile} when it is closed.
     *
     * <p>The caller is responsible for closing the returned stream.
     *
     * @param virtualPath Virtual path of the file to read.
     * @param offset      Byte offset at which to begin reading.
     * @param length      Maximum number of bytes to deliver.
     * @return An {@link InputStream} that yields at most {@code length} bytes
     * starting at {@code offset}.
     * @throws IOException if the file cannot be opened or the seek fails.
     */
    public InputStream openReadRange(String virtualPath, long offset, int length)
            throws IOException {
        File file = resolve(virtualPath);
        RandomAccessFile raf = new RandomAccessFile(file, "r");
        try {
            if (offset > 0) {
                raf.seek(offset);
            }
            return new LimitedRandomAccessInputStream(raf, length);
        } catch (IOException e) {
            // Close the RAF before propagating — caller won't get a stream to close.
            raf.close();
            throw e;
        }
    }

    // ── Write (temp-file pattern for atomicity) ────────────────────────────────

    /**
     * Opens a buffered {@link OutputStream} targeting a temp file for {@code virtualPath}.
     *
     * <p>The temp file is {@code <realPath>.vdtmp}.  Call {@link #finalizeWrite}
     * after all bytes have been written to atomically rename it to the final path.
     *
     * <p>The returned stream is wrapped in a {@link BufferedOutputStream} (buffer size
     * {@value #WRITE_BUFFER_BYTES} bytes) to coalesce TauSync payload chunks into
     * fewer, larger kernel write calls.
     *
     * <p>Parent directories are created automatically.
     *
     * @param virtualPath Destination virtual path.
     * @return An open, buffered {@link OutputStream} pointing at the temp file.
     * @throws IOException on resolution or stream-open failure.
     */
    public OutputStream openWriteTemp(String virtualPath) throws IOException {
        File target = resolve(virtualPath);
        File parent = target.getParentFile();
        if (parent != null && !parent.exists()) {
            if (!parent.mkdirs()) {
                Log.w(TAG, "openWriteTemp: failed to create parent dirs for " + virtualPath);
            }
        }
        File tmp = new File(target.getAbsolutePath() + TMP_SUFFIX);
        return new BufferedOutputStream(new FileOutputStream(tmp), WRITE_BUFFER_BYTES);
    }

    /**
     * Atomically renames the temp file written by {@link #openWriteTemp} to the
     * final destination path, then invalidates the stat / list caches for
     * {@code virtualPath} and its parent.
     *
     * @param virtualPath The destination virtual path used in the corresponding
     *                    {@link #openWriteTemp} call.
     * @throws IOException if the rename fails.
     */
    public void finalizeWrite(String virtualPath) throws IOException {
        File target = resolve(virtualPath);
        File tmp = new File(target.getAbsolutePath() + TMP_SUFFIX);
        if (!tmp.exists()) {
            Log.w(TAG, "finalizeWrite: temp file missing for " + virtualPath);
            return;
        }
        // Delete existing target if present (rename on Android does not overwrite)
        if (target.exists() && !target.delete()) {
            throw new IOException("Could not delete existing file before rename: " + target);
        }
        if (!tmp.renameTo(target)) {
            throw new IOException("Rename failed: " + tmp + " → " + target);
        }
        // Invalidate so the PC sees the updated size/mtime immediately.
        invalidate(virtualPath);
        Log.d(TAG, "finalizeWrite: " + virtualPath + " ✓");
    }

    // ── Create ────────────────────────────────────────────────────────────────

    /**
     * Creates a file or directory at {@code virtualPath}.
     *
     * <p>Parent directories are created automatically for both files and
     * directories.
     *
     * @param virtualPath Virtual path of the new entry.
     * @param isDir       {@code true} to create a directory; {@code false} for a file.
     * @throws IOException if creation fails.
     */
    public void create(String virtualPath, boolean isDir) throws IOException {
        File file = resolve(virtualPath);
        if (isDir) {
            if (!file.mkdirs() && !file.isDirectory()) {
                throw new IOException("Failed to create directory: " + virtualPath);
            }
        } else {
            File parent = file.getParentFile();
            if (parent != null && !parent.exists()) {
                parent.mkdirs();
            }
            if (!file.createNewFile() && !file.exists()) {
                throw new IOException("Failed to create file: " + virtualPath);
            }
        }
        invalidate(virtualPath);
        Log.d(TAG, "create: " + virtualPath + " (isDir=" + isDir + ") ✓");
    }

    // ── Delete ────────────────────────────────────────────────────────────────

    /**
     * Deletes the file or directory (recursively) at {@code virtualPath}.
     *
     * @param virtualPath Virtual path to delete.
     * @throws IOException if the path does not exist or deletion fails.
     */
    public void delete(String virtualPath) throws IOException {
        File file = resolve(virtualPath);
        if (!file.exists()) {
            throw new IOException("Delete target does not exist: " + virtualPath);
        }
        deleteRecursive(file);
        invalidate(virtualPath);
        Log.d(TAG, "delete: " + virtualPath + " ✓");
    }

    private void deleteRecursive(File file) throws IOException {
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children != null) {
                for (File child : children) {
                    deleteRecursive(child);
                }
            }
        }
        if (!file.delete()) {
            throw new IOException("Failed to delete: " + file.getAbsolutePath());
        }
    }

    // ── Rename ────────────────────────────────────────────────────────────────

    /**
     * Renames or moves the entry at {@code fromVirtual} to {@code toVirtual}.
     *
     * @param fromVirtual Source virtual path.
     * @param toVirtual   Destination virtual path.
     * @throws IOException if the source does not exist or the rename fails.
     */
    public void rename(String fromVirtual, String toVirtual) throws IOException {
        File from = resolve(fromVirtual);
        File to = resolve(toVirtual);

        if (!from.exists()) {
            throw new IOException("Rename source does not exist: " + fromVirtual);
        }
        // Create destination parent if needed
        File toParent = to.getParentFile();
        if (toParent != null && !toParent.exists()) {
            toParent.mkdirs();
        }
        if (!from.renameTo(to)) {
            throw new IOException("Rename failed: " + fromVirtual + " → " + toVirtual);
        }
        invalidate(fromVirtual, toVirtual);
        Log.d(TAG, "rename: " + fromVirtual + " → " + toVirtual + " ✓");
    }

    // ── Truncate ──────────────────────────────────────────────────────────────

    /**
     * Sets the length of the file at {@code virtualPath} to {@code newSize} bytes.
     *
     * <p>If {@code newSize} is smaller than the current file size, the file is
     * truncated (bytes beyond {@code newSize} are discarded).  If larger, the file
     * is extended with zero bytes.
     *
     * @param virtualPath Virtual path of the file.
     * @param newSize     Target size in bytes.
     * @throws IOException if the file does not exist or the operation fails.
     */
    public void truncate(String virtualPath, long newSize) throws IOException {
        File file = resolve(virtualPath);
        try (RandomAccessFile raf = new RandomAccessFile(file, "rw")) {
            raf.setLength(newSize);
        }
        invalidate(virtualPath);
        Log.d(TAG, "truncate: " + virtualPath + " → " + newSize + " bytes ✓");
    }

    // ── Cache helpers ─────────────────────────────────────────────────────────

    /**
     * Drops cached stat and list entries for {@code paths} and their immediate
     * parents. Called by every mutation so stale metadata is never served after
     * an in-session change.
     */
    private void invalidate(String... paths) {
        for (String path : paths) {
            statCache.remove(path);
            listCache.remove(path);
            String parent = parentVirtualPath(path);
            if (parent != null) {
                statCache.remove(parent);
                listCache.remove(parent);
            }
        }
        Log.v(TAG, "cache invalidated for: " + java.util.Arrays.toString(paths));
    }

    /**
     * Returns the parent virtual path of {@code path}, or {@code null} for the root.
     *
     * <p>Examples: {@code "/DCIM/Camera"} → {@code "/DCIM"}; {@code "/DCIM"} → {@code "/"};
     * {@code "/"} → {@code null}.
     */
    private static String parentVirtualPath(String path) {
        if (path == null || path.equals("/") || path.isEmpty()) return null;
        int idx = path.lastIndexOf('/');
        if (idx <= 0) return "/";
        return path.substring(0, idx);
    }

    /**
     * Joins a parent virtual path and a child entry name into a normalized path.
     *
     * <p>Example: {@code ("/DCIM", "Camera")} → {@code "/DCIM/Camera"};
     * {@code ("/", "DCIM")} → {@code "/DCIM"}.
     */
    private static String childVirtualPath(String parent, String name) {
        return "/".equals(parent) ? "/" + name : parent + "/" + name;
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private static VDriveEntry fileToEntry(File file, String name) {
        boolean isDir = file.isDirectory();
        long size = isDir ? 0L : file.length();
        return new VDriveEntry(name, isDir, size, file.lastModified());
    }

    // ── Paginated directory listing ───────────────────────────────────────────

    /**
     * Immutable result of a single {@link #listDirPage} call.
     *
     * <p>Entries are a name-sorted page starting just after {@code afterName}.
     * {@code hasMore} is {@code true} when at least one more entry exists beyond
     * this page; {@code nextAfter} is the last entry name in this page and should
     * be passed as {@code afterName} on the next call to continue pagination.
     */
    public static final class ListPageResult {
        @NonNull
        public final List<VDriveEntry> entries;
        public final boolean hasMore;
        @Nullable
        public final String nextAfter; // null when !hasMore

        public ListPageResult(@NonNull List<VDriveEntry> entries,
                              boolean hasMore,
                              @Nullable String nextAfter) {
            this.entries = entries;
            this.hasMore = hasMore;
            this.nextAfter = nextAfter;
        }
    }

    /**
     * Returns a page of up to {@code limit} children of {@code virtualPath},
     * sorted alphabetically by name, starting just after {@code afterName}.
     *
     * <p>Pass {@code afterName = null} to start from the beginning.  On each
     * subsequent call pass {@link ListPageResult#nextAfter} as {@code afterName}
     * to advance the cursor.  When {@link ListPageResult#hasMore} is {@code false}
     * the listing is exhausted.
     *
     * <p>This method always re-reads {@code dir.listFiles()} so the sort is
     * deterministic even if external tools modify the directory between pages.
     * For typical use (single Explorer open session) the OS page cache makes this
     * fast.
     *
     * @param virtualPath Virtual path of the directory to list.
     * @param afterName   Exclusive lower bound (last name from previous page),
     *                    or {@code null} to start from the first entry.
     * @param limit       Maximum number of entries to return.
     * @return A {@link ListPageResult} with up to {@code limit} entries.
     * @throws IOException       on path resolution failure.
     * @throws SecurityException on traversal attempt.
     */
    public ListPageResult listDirPage(String virtualPath,
                                      @Nullable String afterName,
                                      int limit) throws IOException {
        File dir = resolve(virtualPath);
        if (!dir.isDirectory()) {
            Log.w(TAG, "listDirPage: not a directory — " + virtualPath);
            return new ListPageResult(new ArrayList<>(), false, null);
        }

        File[] children = dir.listFiles();
        if (children == null || children.length == 0) {
            return new ListPageResult(new ArrayList<>(), false, null);
        }

        // Sort by name for a stable cursor across pages.
        Arrays.sort(children, (a, b) -> a.getName().compareTo(b.getName()));

        // Find the first index after 'afterName' (binary search on sorted array).
        int start = 0;
        if (afterName != null) {
            for (int i = 0; i < children.length; i++) {
                if (children[i].getName().equals(afterName)) {
                    start = i + 1;
                    break;
                }
            }
        }

        // Collect the page.
        int end = Math.min(start + limit, children.length);
        List<VDriveEntry> page = new ArrayList<>(end - start);
        for (int i = start; i < end; i++) {
            page.add(fileToEntry(children[i], children[i].getName()));
        }

        boolean hasMore = end < children.length;
        String nextAfter = (!page.isEmpty()) ? page.get(page.size() - 1).getName() : null;
        return new ListPageResult(page, hasMore, nextAfter);
    }

    // ── LimitedRandomAccessInputStream ────────────────────────────────────────

    /**
     * Wraps a {@link RandomAccessFile} (already seeked to the correct offset) and
     * limits the number of bytes that can be read from it.  Used by
     * {@link #openReadRange} to honour the {@code length} parameter of a WinFsp
     * read request.
     *
     * <p>Closing this stream closes the underlying {@link RandomAccessFile}.
     */
    private static final class LimitedRandomAccessInputStream extends InputStream {

        private final RandomAccessFile raf;
        private int remaining;

        LimitedRandomAccessInputStream(RandomAccessFile raf, int limit) {
            this.raf = raf;
            this.remaining = limit;
        }

        @Override
        public int read() throws IOException {
            if (remaining <= 0) return -1;
            int b = raf.read();
            if (b >= 0) remaining--;
            return b;
        }

        @Override
        public int read(byte[] buf, int off, int len) throws IOException {
            if (remaining <= 0) return -1;
            int n = raf.read(buf, off, Math.min(len, remaining));
            if (n > 0) remaining -= n;
            return n;
        }

        @Override
        public void close() throws IOException {
            raf.close();
        }
    }
}

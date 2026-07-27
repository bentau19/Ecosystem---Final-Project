package com.example.android.data.datasource;

import android.os.Environment;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;
import android.system.StructStat;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import com.example.android.domain.entities.VDriveEntry;
import com.example.android.domain.entities.VDrivePageResult;
import com.example.android.domain.entities.VDriveReadRange;
import com.example.android.domain.exceptions.VDriveException;
import com.example.android.utils.StoragePermissions;

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
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * File I/O for the virtual drive: maps virtual paths 1:1 to external storage.
 * On-demand request→response — no background scan or index.
 * In-memory cache absorbs WinFsp stat storms; mutations invalidate affected entries.
 */
public class VirtualDriveDataSource {

    private static final String TAG = "VirtualDriveDS";

    private static final String TMP_SUFFIX = ".vdtmp";             // avoids partial-write visibility
    private static final long CACHE_TTL_MS = 3_000L;              // 3 s — absorbs WinFsp storms
    private static final int  CACHE_TTL_S  = 3;
    private static final int  WRITE_BUFFER_BYTES = 256 * 1024;    // 256 KB write buffer
    private static final int  MAX_IDLE_READ_HANDLES = 16;         // soft fd-budget cap
    private static final long READ_HANDLE_IDLE_MS   = 15_000L;    // evict handles idle > 15 s

    /** Canonical path of the storage root — used for traversal validation. */
    private final String storageRoot;

    // ── In-memory caches ──────────────────────────────────────────────────────

    private record CacheEntry<T>(T value, long expiryMs) {}

    /** Stat cache: absorbs per-entry probes after a ReadDirectory. */
    private final ConcurrentHashMap<String, CacheEntry<VDriveEntry>> statCache =
            new ConcurrentHashMap<>();

    /** List cache: absorbs repeated ReadDirectory refreshes. */
    private final ConcurrentHashMap<String, CacheEntry<List<VDriveEntry>>> listCache =
            new ConcurrentHashMap<>();

    /** Sorted-snapshot cache: reused across successive listDirPage cursor calls. */
    private final ConcurrentHashMap<String, CacheEntry<File[]>> sortedChildCache =
            new ConcurrentHashMap<>();

    // ── Read-handle pool ──────────────────────────────────────────────────────

    private static final class PooledReader {
        final RandomAccessFile raf;
        volatile long idleSinceMs;
        PooledReader(RandomAccessFile raf) { this.raf = raf; }
    }

    // one idle handle per path; sequential reads reuse it (just a seek, no re-open)
    private final ConcurrentHashMap<String, PooledReader> idleReaders =
            new ConcurrentHashMap<>();

    /** Approximate count of pooled handles; soft-bounds the fd budget. */
    private final AtomicInteger idleReaderCount = new AtomicInteger();

    public VirtualDriveDataSource() {
        File root = Environment.getExternalStorageDirectory();
        try {
            storageRoot = root.getCanonicalPath();
        } catch (IOException e) {
            throw new IllegalStateException("Cannot determine external storage root", e);
        }
    }

    // ── Write gate ────────────────────────────────────────────────────────────

    /**
     * Fails fast when shared storage is not writable through the File API.
     *
     * <p>Every write here goes through raw {@code java.io.File}. Under scoped
     * storage that only works while All files access is granted; without it
     * MediaProvider's FUSE daemon rejects the underlying {@code open(O_CREAT)}
     * with {@code EPERM}, whose message ("Operation not permitted") means nothing
     * to Windows and surfaces in Explorer as a generic I/O device error. Reads
     * and directory listings are unaffected, so the drive mounts and browses
     * normally and only copies fail — checking up front turns that into a
     * deliberate {@code access_denied} the PC can explain.
     */
    private void requireWritable(String virtualPath) throws VDriveException {
        if (!StoragePermissions.hasAllFilesAccess()) {
            Log.w(TAG, "write refused (no All files access): " + virtualPath);
            throw new VDriveException("access_denied",
                    "All files access not granted — cannot write " + virtualPath);
        }
    }

    // ── Path resolution ───────────────────────────────────────────────────────

    /** Maps a virtual path to the corresponding File on disk. Throws SecurityException on traversal. */
    public File resolve(String virtualPath) throws IOException {
        String relative = virtualPath.startsWith("/") ? virtualPath.substring(1) : virtualPath;
        File resolved = new File(storageRoot, relative);
        String canonical = resolved.getCanonicalPath();
        if (!canonical.startsWith(storageRoot)) {
            throw new SecurityException("Virtual path escapes storage root: " + virtualPath);
        }
        return resolved;
    }

    // ── Directory listing ─────────────────────────────────────────────────────

    /** Lists direct children of virtualPath. Serves from cache when warm. */
    public List<VDriveEntry> listDir(String virtualPath) throws IOException {
        // restricted subtrees block without returning data — short-circuit entirely
        if (isRestrictedDir(virtualPath) || isRestrictedDescendant(virtualPath)) {
            return new ArrayList<>();
        }

        // cache
        CacheEntry<List<VDriveEntry>> hit = listCache.get(virtualPath);
        if (hit != null && hit.expiryMs() > System.currentTimeMillis()) {
            Log.v(TAG, "listDir cache hit: " + virtualPath);
            return hit.value();
        }

        // filesystem
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
                    // hide /Android/data and /Android/obb — inaccessible via File API
                    if (isRestrictedDir(childVirtualPath(virtualPath, child.getName()))) continue;
                    entries.add(fileToEntry(child, child.getName()));
                }
            }
        }

        Log.d(TAG, "listDir (fs): " + entries.size() + " entries for " + virtualPath);
        return cacheAndReturnList(virtualPath, entries);
    }

    // ── Stat ──────────────────────────────────────────────────────────────────

    /** Returns metadata for virtualPath, or null if it does not exist. Serves from cache when warm. */
    public @Nullable VDriveEntry stat(String virtualPath) throws IOException {
        // Restricted roots (/Android/data, /Android/obb) exist on disk but their contents
        // are inaccessible on Android 11+. Os.stat() on FUSE-mediated paths can block
        // indefinitely — stalling TauSync and tearing the WinFsp drive down. Short-circuit
        // to null here so genuinely missing paths still report not-found correctly.

        // cache
        CacheEntry<VDriveEntry> hit = statCache.get(virtualPath);
        if (hit != null && hit.expiryMs() > System.currentTimeMillis()) {
            Log.v(TAG, "stat cache hit: " + virtualPath);
            return hit.value();
        }

        // filesystem
        File file = resolve(virtualPath);
        if (!file.exists()) {
            return null;
        }
        VDriveEntry entry = fileToEntry(file, file.getName());
        statCache.put(virtualPath,
                new CacheEntry<>(entry, System.currentTimeMillis() + CACHE_TTL_MS));
        Log.v(TAG, "stat (fs): " + virtualPath);
        return entry;
    }

    // ── Paginated directory listing ────────────────────────────────────────────

    /** Returns a sorted page of up to limit children starting after afterName. */
    public VDrivePageResult listDirPage(String virtualPath,
                                        @Nullable String afterName,
                                        int limit) throws IOException {
        if (isRestrictedDir(virtualPath) || isRestrictedDescendant(virtualPath)) {
            return new VDrivePageResult(new ArrayList<>(), false, null);
        }

        File[] children;
        CacheEntry<File[]> snap = sortedChildCache.get(virtualPath);
        if (snap != null && snap.expiryMs() > System.currentTimeMillis()) {
            children = snap.value();
            Log.v(TAG, "listDirPage snapshot hit: " + virtualPath);
        } else {
            File dir = resolve(virtualPath);
            if (!dir.isDirectory()) {
                Log.w(TAG, "listDirPage: not a directory — " + virtualPath);
                return new VDrivePageResult(new ArrayList<>(), false, null);
            }
            File[] all = dir.listFiles();
            if (all == null) all = new File[0];

            // filter restricted roots before sorting so the cursor operates on visible set only
            List<File> visible = new ArrayList<>(all.length);
            for (File child : all) {
                if (!isRestrictedDir(childVirtualPath(virtualPath, child.getName()))) {
                    visible.add(child);
                }
            }
            children = visible.toArray(new File[0]);

            Arrays.sort(children, (a, b) -> a.getName().compareTo(b.getName()));

            sortedChildCache.put(virtualPath,
                    new CacheEntry<>(children, System.currentTimeMillis() + CACHE_TTL_MS));
            Log.d(TAG, "listDirPage (fs): sorted " + children.length
                    + " entries for " + virtualPath);
        }

        if (children.length == 0) {
            return new VDrivePageResult(new ArrayList<>(), false, null);
        }

        // binary-search cursor on sorted snapshot
        int start = 0;
        if (afterName != null) {
            int lo = 0, hi = children.length - 1;
            while (lo <= hi) {
                int mid = (lo + hi) >>> 1;
                int cmp = children[mid].getName().compareTo(afterName);
                if (cmp < 0) {
                    lo = mid + 1;
                } else if (cmp > 0) {
                    hi = mid - 1;
                } else {
                    lo = mid + 1;
                    break;
                }
            }
            start = lo;
        }

        int end = Math.min(start + limit, children.length);
        List<VDriveEntry> page = new ArrayList<>(end - start);
        for (int i = start; i < end; i++) {
            page.add(fileToEntry(children[i], children[i].getName()));
        }

        boolean hasMore = end < children.length;
        String nextAfter = (!page.isEmpty()) ? page.get(page.size() - 1).getName() : null;
        return new VDrivePageResult(page, hasMore, nextAfter);
    }

    // ── Read ──────────────────────────────────────────────────────────────────

    /** Opens an InputStream for bytes [offset, offset+length) of virtualPath. */
    public InputStream openReadRange(String virtualPath, long offset, int length)
            throws IOException {
        if (isRestrictedDescendant(virtualPath)) {
            throw new java.io.FileNotFoundException("Restricted path: " + virtualPath);
        }
        File file = resolve(virtualPath);
        RandomAccessFile raf = checkoutReader(virtualPath);
        if (raf == null) {
            raf = new RandomAccessFile(file, "r");
        }
        try {
            // always seek — a reused handle is positioned at the previous read's end
            raf.seek(offset);
            return new PooledLimitedInputStream(virtualPath, raf, length);
        } catch (IOException e) {
            raf.close();
            throw e;
        }
    }

    /**
     * Like openReadRange but also returns the exact byte count the stream will yield,
     * so the caller can frame the response and the peer can detect truncation.
     */
    public VDriveReadRange openReadRangeChecked(String virtualPath, long offset, int length)
            throws IOException {
        if (isRestrictedDescendant(virtualPath)) {
            throw new java.io.FileNotFoundException("Restricted path: " + virtualPath);
        }
        File file = resolve(virtualPath);
        RandomAccessFile raf = checkoutReader(virtualPath);
        if (raf == null) {
            raf = new RandomAccessFile(file, "r");
        }
        try {
            long fileLen = raf.length();
            long available = Math.max(0L, Math.min((long) length, fileLen - offset));
            raf.seek(offset);
            InputStream in = new PooledLimitedInputStream(virtualPath, raf, (int) available);
            return new VDriveReadRange(available, in);
        } catch (IOException e) {
            raf.close();
            throw e;
        }
    }

    /** Returns true if virtualPath resolves to an existing entry. */
    public boolean exists(String virtualPath) {
        if (isRestrictedDescendant(virtualPath)) return false;
        try {
            return resolve(virtualPath).exists();
        } catch (IOException e) {
            return false;
        }
    }

    // ── Read-handle pool helpers ──────────────────────────────────────────────

    // remove and return the idle handle for path, or null
    private RandomAccessFile checkoutReader(String path) {
        PooledReader pr = idleReaders.remove(path);
        if (pr == null) return null;
        idleReaderCount.decrementAndGet();
        return pr.raf;
    }

    // return handle to pool, or close it if pool is full / handle is unhealthy
    private void checkinReader(String path, RandomAccessFile raf, boolean healthy) {
        if (!healthy || idleReaderCount.get() >= MAX_IDLE_READ_HANDLES) {
            closeQuietly(raf);
            return;
        }
        PooledReader pr = new PooledReader(raf);
        pr.idleSinceMs = System.currentTimeMillis();
        if (idleReaders.putIfAbsent(path, pr) != null) {
            closeQuietly(raf); // already a handle parked for this path
            return;
        }
        idleReaderCount.incrementAndGet();
        sweepIdleReaders();
    }

    // close and drop the pooled handle for path, if any
    private void evictReader(String path) {
        PooledReader pr = idleReaders.remove(path);
        if (pr != null) {
            idleReaderCount.decrementAndGet();
            closeQuietly(pr.raf);
        }
    }

    // close handles idle longer than READ_HANDLE_IDLE_MS
    private void sweepIdleReaders() {
        long now = System.currentTimeMillis();
        for (Map.Entry<String, PooledReader> e : idleReaders.entrySet()) {
            PooledReader pr = e.getValue();
            if (now - pr.idleSinceMs > READ_HANDLE_IDLE_MS
                    && idleReaders.remove(e.getKey(), pr)) {
                idleReaderCount.decrementAndGet();
                closeQuietly(pr.raf);
            }
        }
    }

    private static void closeQuietly(RandomAccessFile raf) {
        try { raf.close(); } catch (IOException ignored) {}
    }

    // ── Write (temp-file pattern for atomicity) ────────────────────────────────

    /** Opens a buffered OutputStream to the temp file for virtualPath. */
    public OutputStream openWriteTemp(String virtualPath) throws IOException {
        requireWritable(virtualPath);
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

    /** Atomically renames the temp file to the final path and invalidates caches. */
    public void finalizeWrite(String virtualPath) throws IOException {
        File target = resolve(virtualPath);
        File tmp = new File(target.getAbsolutePath() + TMP_SUFFIX);
        if (!tmp.exists()) {
            Log.w(TAG, "finalizeWrite: temp file missing for " + virtualPath);
            return;
        }
        if (target.exists() && !target.delete()) {
            throw new IOException("Could not delete existing file before rename: " + target);
        }
        if (!tmp.renameTo(target)) {
            throw new IOException("Rename failed: " + tmp + " → " + target);
        }
        invalidate(virtualPath);
        Log.d(TAG, "finalizeWrite: " + virtualPath + " ✓");
    }

    // ── Create ────────────────────────────────────────────────────────────────

    /** Creates a file or directory at virtualPath. */
    public void create(String virtualPath, boolean isDir) throws IOException {
        requireWritable(virtualPath);
        if (isRestrictedDir(virtualPath) || isRestrictedDescendant(virtualPath)) {
            throw new IOException("Path is not writable: " + virtualPath);
        }
        File file = resolve(virtualPath);
        if (isDir) {
            if (!file.mkdirs() && !file.isDirectory()) {
                throw new IOException("Failed to create directory: " + virtualPath);
            }
        } else {
            File parent = file.getParentFile();
            if (parent != null && !parent.exists()) parent.mkdirs();
            if (!file.createNewFile() && !file.exists()) {
                throw new IOException("Failed to create file: " + virtualPath);
            }
        }
        invalidate(virtualPath);
        Log.d(TAG, "create: " + virtualPath + " (isDir=" + isDir + ") ✓");
    }

    // ── Delete ────────────────────────────────────────────────────────────────

    /** Deletes the file or directory (recursively) at virtualPath. */
    public void delete(String virtualPath) throws IOException {
        requireWritable(virtualPath);
        if (isRestrictedDir(virtualPath) || isRestrictedDescendant(virtualPath)) {
            throw new IOException("Path is not writable: " + virtualPath);
        }
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
                for (File child : children) deleteRecursive(child);
            }
        }
        if (!file.delete()) {
            throw new IOException("Failed to delete: " + file.getAbsolutePath());
        }
    }

    // ── Rename ────────────────────────────────────────────────────────────────

    /** Renames or moves fromVirtual to toVirtual. */
    public void rename(String fromVirtual, String toVirtual) throws IOException {
        requireWritable(toVirtual);
        if (isRestrictedDir(fromVirtual) || isRestrictedDescendant(fromVirtual)
                || isRestrictedDir(toVirtual) || isRestrictedDescendant(toVirtual)) {
            throw new IOException("Path is not writable: " + fromVirtual + " → " + toVirtual);
        }
        File from = resolve(fromVirtual);
        File to = resolve(toVirtual);
        if (!from.exists()) {
            throw new IOException("Rename source does not exist: " + fromVirtual);
        }
        File toParent = to.getParentFile();
        if (toParent != null && !toParent.exists()) toParent.mkdirs();
        if (!from.renameTo(to)) {
            throw new IOException("Rename failed: " + fromVirtual + " → " + toVirtual);
        }
        invalidate(fromVirtual, toVirtual);
        Log.d(TAG, "rename: " + fromVirtual + " → " + toVirtual + " ✓");
    }

    // ── Truncate ──────────────────────────────────────────────────────────────

    /** Sets the length of the file at virtualPath to newSize bytes. */
    public void truncate(String virtualPath, long newSize) throws IOException {
        requireWritable(virtualPath);
        if (isRestrictedDir(virtualPath) || isRestrictedDescendant(virtualPath)) {
            throw new IOException("Path is not writable: " + virtualPath);
        }
        File file = resolve(virtualPath);
        try (RandomAccessFile raf = new RandomAccessFile(file, "rw")) {
            raf.setLength(newSize);
        }
        invalidate(virtualPath);
        Log.d(TAG, "truncate: " + virtualPath + " → " + newSize + " bytes ✓");
    }

    // ── Cache invalidation ────────────────────────────────────────────────────

    // evicts cache entries for paths and their parents; called by every mutation
    private void invalidate(String... paths) {
        for (String path : paths) {
            statCache.remove(path);
            listCache.remove(path);
            sortedChildCache.remove(path);
            evictReader(path); // stale content after write/rename/truncate/delete
            String parent = parentVirtualPath(path);
            if (parent != null) {
                statCache.remove(parent);
                listCache.remove(parent);
                sortedChildCache.remove(parent);
            }
        }
        Log.v(TAG, "invalidated caches for: " + Arrays.toString(paths));
    }

    // ── Restricted-subtree guards ─────────────────────────────────────────────

    // /Android/data and /Android/obb: FUSE-mediated, File API blocks on them —
    // short-circuit to empty/not-found without touching the filesystem
    private static final String[] RESTRICTED_ROOTS = {"/Android/data", "/Android/obb"};

    private static boolean isRestrictedDir(String virtualPath) {
        for (String root : RESTRICTED_ROOTS) {
            if (root.equals(virtualPath)) return true;
        }
        return false;
    }

    private static boolean isRestrictedDescendant(String virtualPath) {
        if (virtualPath == null) return false;
        for (String root : RESTRICTED_ROOTS) {
            if (virtualPath.startsWith(root + "/")) return true;
        }
        return false;
    }

    // ── Path helpers ──────────────────────────────────────────────────────────

    private static String parentVirtualPath(String path) {
        if (path == null || path.equals("/") || path.isEmpty()) return null;
        int idx = path.lastIndexOf('/');
        if (idx <= 0) return "/";
        return path.substring(0, idx);
    }

    private static String childVirtualPath(String parent, String name) {
        return "/".equals(parent) ? "/" + name : parent + "/" + name;
    }

    // ── VDriveEntry conversion ────────────────────────────────────────────────

    private static VDriveEntry fileToEntry(File file, String name) {
        // Os.stat() returns mode+size+mtime in one syscall vs three File.isX() calls
        try {
            StructStat st = Os.stat(file.getAbsolutePath());
            boolean isDir = OsConstants.S_ISDIR(st.st_mode);
            return new VDriveEntry(name, isDir, isDir ? 0L : st.st_size, st.st_mtime * 1000L);
        } catch (ErrnoException e) {
            boolean isDir = file.isDirectory();
            return new VDriveEntry(name, isDir, isDir ? 0L : file.length(), file.lastModified());
        }
    }

    // ── Cache population helper ───────────────────────────────────────────────

    private List<VDriveEntry> cacheAndReturnList(String virtualPath, List<VDriveEntry> entries) {
        long expiry = System.currentTimeMillis() + CACHE_TTL_MS;
        listCache.put(virtualPath, new CacheEntry<>(entries, expiry));
        // seed stat cache so post-ReadDirectory stat probes are answered from cache
        for (VDriveEntry e : entries) {
            String childPath = childVirtualPath(virtualPath, e.getName());
            statCache.put(childPath, new CacheEntry<>(e, expiry));
        }
        return entries;
    }

    // ── PooledLimitedInputStream ──────────────────────────────────────────────

    // limits bytes from a pooled RandomAccessFile; returns handle to pool on close
    private final class PooledLimitedInputStream extends InputStream {

        private final String path;
        private final RandomAccessFile raf;
        private int remaining;
        private boolean healthy = true;
        private boolean closed = false;

        PooledLimitedInputStream(String path, RandomAccessFile raf, int limit) {
            this.path = path;
            this.raf = raf;
            this.remaining = limit;
        }

        @Override
        public int read() throws IOException {
            if (remaining <= 0) return -1;
            try {
                int b = raf.read();
                if (b >= 0) remaining--;
                return b;
            } catch (IOException e) {
                healthy = false;
                throw e;
            }
        }

        @Override
        public int read(byte[] buf, int off, int len) throws IOException {
            if (remaining <= 0) return -1;
            try {
                int n = raf.read(buf, off, Math.min(len, remaining));
                if (n > 0) remaining -= n;
                return n;
            } catch (IOException e) {
                healthy = false;
                throw e;
            }
        }

        @Override
        public void close() {
            if (closed) return;
            closed = true;
            checkinReader(path, raf, healthy);
        }
    }
}

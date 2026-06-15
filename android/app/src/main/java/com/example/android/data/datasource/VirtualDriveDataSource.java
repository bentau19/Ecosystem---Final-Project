package com.example.android.data.datasource;

import android.os.Environment;
import android.util.Log;

import com.example.android.domain.entities.VDriveEntry;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.RandomAccessFile;
import java.util.ArrayList;
import java.util.List;

/**
 * File I/O layer for the virtual drive feature.
 *
 * <p>All operations map the virtual path space (rooted at {@code "/"}) onto the
 * device's primary external storage ({@link Environment#getExternalStorageDirectory()},
 * i.e. {@code /storage/emulated/0/}).
 *
 * <p><b>Path traversal safety</b>: {@link #resolve} validates that the canonical
 * absolute path of every resolved file starts with the storage root — any attempt
 * to escape via {@code ".."} components throws a {@link SecurityException}.
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

    /** Temp-file suffix used during write sessions to avoid partial writes being visible. */
    private static final String TMP_SUFFIX = ".vdtmp";

    /** Canonical absolute path of the storage root — used for traversal validation. */
    private final String storageRoot;

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
     * @param virtualPath Virtual path of the directory to list.
     * @return List of {@link VDriveEntry} objects; empty if the directory is
     *         empty or the path is not a readable directory.
     * @throws IOException       on path resolution failure.
     * @throws SecurityException on traversal attempt.
     */
    public List<VDriveEntry> listDir(String virtualPath) throws IOException {
        File dir = resolve(virtualPath);
        List<VDriveEntry> entries = new ArrayList<>();

        if (!dir.isDirectory()) {
            Log.w(TAG, "listDir: not a directory — " + virtualPath);
            return entries;
        }

        File[] children = dir.listFiles();
        if (children == null) {
            Log.w(TAG, "listDir: listFiles() returned null for " + virtualPath);
            return entries;
        }

        for (File child : children) {
            entries.add(fileToEntry(child));
        }
        return entries;
    }

    // ── Stat ──────────────────────────────────────────────────────────────────

    /**
     * Returns metadata for the file or directory at {@code virtualPath}, or
     * {@code null} if it does not exist.
     *
     * @param virtualPath Virtual path of the target.
     * @return {@link VDriveEntry} if the path exists; {@code null} otherwise.
     * @throws IOException       on path resolution failure.
     * @throws SecurityException on traversal attempt.
     */
    public VDriveEntry stat(String virtualPath) throws IOException {
        File file = resolve(virtualPath);
        if (!file.exists()) {
            return null;
        }
        return fileToEntry(file);
    }

    // ── Read ──────────────────────────────────────────────────────────────────

    /**
     * Opens a size-limited {@link InputStream} for the byte range
     * [{@code offset}, {@code offset + length}) of the file at
     * {@code virtualPath}.
     *
     * <p>The caller is responsible for closing the returned stream.
     *
     * @param virtualPath Virtual path of the file to read.
     * @param offset      Byte offset at which to begin reading.
     * @param length      Maximum number of bytes to deliver.
     * @return An {@link InputStream} that yields at most {@code length} bytes
     *         starting at {@code offset}.
     * @throws IOException if the file cannot be opened or the skip fails.
     */
    public InputStream openReadRange(String virtualPath, long offset, int length)
            throws IOException {
        File file = resolve(virtualPath);
        FileInputStream fis = new FileInputStream(file);
        if (offset > 0) {
            long skipped = 0;
            while (skipped < offset) {
                long s = fis.skip(offset - skipped);
                if (s <= 0) break;
                skipped += s;
            }
        }
        return new LimitedInputStream(fis, length);
    }

    // ── Write (temp-file pattern for atomicity) ────────────────────────────────

    /**
     * Opens a {@link FileOutputStream} targeting a temp file for {@code virtualPath}.
     *
     * <p>The temp file is {@code <realPath>.vdtmp}.  Call {@link #finalizeWrite}
     * after all bytes have been written to atomically rename it to the final path.
     *
     * <p>Parent directories are created automatically.
     *
     * @param virtualPath Destination virtual path.
     * @return An open {@link FileOutputStream} pointing at the temp file.
     * @throws IOException on resolution or stream-open failure.
     */
    public FileOutputStream openWriteTemp(String virtualPath) throws IOException {
        File target = resolve(virtualPath);
        File parent = target.getParentFile();
        if (parent != null && !parent.exists()) {
            if (!parent.mkdirs()) {
                Log.w(TAG, "openWriteTemp: failed to create parent dirs for " + virtualPath);
            }
        }
        File tmp = new File(target.getAbsolutePath() + TMP_SUFFIX);
        return new FileOutputStream(tmp);
    }

    /**
     * Atomically renames the temp file written by {@link #openWriteTemp} to the
     * final destination path.
     *
     * @param virtualPath The destination virtual path used in the corresponding
     *                    {@link #openWriteTemp} call.
     * @throws IOException if the rename fails.
     */
    public void finalizeWrite(String virtualPath) throws IOException {
        File target = resolve(virtualPath);
        File tmp    = new File(target.getAbsolutePath() + TMP_SUFFIX);
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
        File to   = resolve(toVirtual);

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
        Log.d(TAG, "truncate: " + virtualPath + " → " + newSize + " bytes ✓");
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    /**
     * Builds a {@link VDriveEntry} from a {@link File} that is known to exist.
     */
    private static VDriveEntry fileToEntry(File file) {
        String name    = file.getName();
        boolean isDir  = file.isDirectory();
        long size      = isDir ? 0L : file.length();
        long mtimeMs   = file.lastModified();  // already in milliseconds
        return new VDriveEntry(name, isDir, size, mtimeMs);
    }

    // ── LimitedInputStream ────────────────────────────────────────────────────

    /**
     * Wraps an existing {@link InputStream} and limits the number of bytes
     * that can be read from it.  Used by {@link #openReadRange} to honour the
     * {@code length} parameter of a WinFsp read request.
     */
    private static final class LimitedInputStream extends InputStream {

        private final InputStream wrapped;
        private int remaining;

        LimitedInputStream(InputStream wrapped, int limit) {
            this.wrapped   = wrapped;
            this.remaining = limit;
        }

        @Override
        public int read() throws IOException {
            if (remaining <= 0) return -1;
            int b = wrapped.read();
            if (b >= 0) remaining--;
            return b;
        }

        @Override
        public int read(byte[] buf, int off, int len) throws IOException {
            if (remaining <= 0) return -1;
            int n = wrapped.read(buf, off, Math.min(len, remaining));
            if (n > 0) remaining -= n;
            return n;
        }

        @Override
        public void close() throws IOException {
            wrapped.close();
        }
    }
}

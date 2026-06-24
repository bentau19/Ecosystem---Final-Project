package com.example.android.domain.entities;

import org.json.JSONException;
import org.json.JSONObject;

/**
 * Metadata for a single file or folder on the phone's storage.
 *
 * Mirrors the desktop's {@code VDriveEntryDTO} exactly so the JSON wire format
 * is compatible with the C++ WinFsp callbacks that consume it
 * ({@code ReadDirectory}, {@code Open}, {@code GetFileInfo}).
 *
 * <p>Wire JSON fields:
 * <pre>
 *   name     — basename of the file or folder (no directory component)
 *   is_dir   — true if this entry is a directory
 *   size     — size in bytes; always 0 for directories
 *   mtime_ms — last-modified timestamp in Unix epoch milliseconds (0 = unavailable)
 * </pre>
 *
 * <p>This is a pure Java value object — no Android Framework imports.
 */
public final class VDriveEntry {

    private final String name;
    private final boolean isDir;
    private final long size;
    private final long mtimeMs;

    public VDriveEntry(String name, boolean isDir, long size, long mtimeMs) {
        this.name    = name;
        this.isDir   = isDir;
        this.size    = size;
        this.mtimeMs = mtimeMs;
    }

    // ── Accessors ─────────────────────────────────────────────────────────────

    public String getName()    { return name;    }
    public boolean isDir()     { return isDir;   }
    public long getSize()      { return size;    }
    public long getMtimeMs()   { return mtimeMs; }

    // ── Serialization ─────────────────────────────────────────────────────────

    /**
     * Serialises this entry to a JSON object matching the desktop's wire format.
     *
     * <pre>{"name": "photo.jpg", "is_dir": false, "size": 123456, "mtime_ms": 1718000000000}</pre>
     */
    public JSONObject toJson() throws JSONException {
        JSONObject obj = new JSONObject();
        obj.put("name",     name);
        obj.put("is_dir",   isDir);
        obj.put("size",     size);
        obj.put("mtime_ms", mtimeMs);
        return obj;
    }

    @Override
    public String toString() {
        return "VDriveEntry{name='" + name + "', isDir=" + isDir
                + ", size=" + size + ", mtimeMs=" + mtimeMs + "}";
    }
}

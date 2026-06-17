package com.example.android.domain.usecases;

import android.util.Log;

import com.example.android.data.datasource.VirtualDriveDataSource;
import com.example.android.domain.entities.VDriveEntry;
import com.example.android.network.transport.TransportManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;

/**
 * Coordinates all virtual-drive operations between the TauSync transport layer
 * and the local file system.
 *
 * <p>Each public method handles one WinFsp operation forwarded by the desktop's
 * {@code VirtualDriveService}.  The desktop generates a unique per-request meeting word
 * ({@code {base}_{uuid8}}, e.g. {@code "virtual_drive_stat_a1b2c3d4"}) for every op, so
 * every method receives the <em>exact</em> channel name to connect on.
 *
 * <h3>Protocol</h3>
 * <ul>
 *   <li><b>Simple ops</b> (list / stat / create / delete / rename / truncate): one
 *       {@link TransportManager#serveJsonExchange} call — PC writes JSON request line,
 *       Android writes JSON response, channel closes.
 *   <li><b>Read</b>: one {@link TransportManager#serveJsonThenStreamOut} call — PC writes
 *       {@code {path, offset, length}\n}, Android opens the file range and streams the
 *       bytes back until EOF.
 *   <li><b>Write</b>: one {@link TransportManager#serveJsonHeaderThenStreamIn} call — PC
 *       writes {@code {path}\n} header then pushes the file bytes until {@code write_close}
 *       closes the stream.  Android pipes the bytes into a temp file; after the method
 *       returns (OutputStream closed) {@link VirtualDriveDataSource#finalizeWrite} atomically
 *       renames the temp file to its final path.
 * </ul>
 *
 * <p>All methods must be called from a background thread — they block on network I/O.
 * No dedicated data threads are spawned; streaming happens inline on the calling thread
 * via the chunked transport primitives.
 */
public class VirtualDriveUseCase {

    private static final String TAG = "VirtualDriveUC";

    private final TransportManager transportManager;
    private final VirtualDriveDataSource dataSource;

    public VirtualDriveUseCase(TransportManager transportManager,
                               VirtualDriveDataSource dataSource) {
        this.transportManager = transportManager;
        this.dataSource = dataSource;
    }

    // ── list ──────────────────────────────────────────────────────────────────

    /**
     * Serves a {@code virtual_drive_list_{uuid8}} request.
     *
     * <p>PC sends {@code {"path": "..."}}.  Android responds with:
     * <pre>{"ok": true, "entries": [{"name","is_dir","size","mtime_ms"}, ...]}</pre>
     * or {@code {"ok": false, "error": "..."}} on failure.
     *
     * @param channel The exact meeting word the desktop opened (includes UUID suffix).
     */
    public void handleList(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        String path = req.getString("path");
                        List<VDriveEntry> entries = dataSource.listDir(path);

                        JSONArray arr = new JSONArray();
                        for (VDriveEntry e : entries) {
                            arr.put(e.toJson());
                        }
                        JSONObject resp = new JSONObject();
                        resp.put("ok", true);
                        resp.put("entries", arr);
                        return resp.toString();
                    } catch (Exception e) {
                        Log.e(TAG, "handleList error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── stat ──────────────────────────────────────────────────────────────────

    /**
     * Serves a {@code virtual_drive_stat_{uuid8}} request.
     *
     * <p>PC sends {@code {"path": "..."}}.  Android responds with the entry's
     * fields inlined at the top level ({@code {"ok":true,"name","is_dir","size","mtime_ms"}})
     * or {@code {"ok": false}} if the path does not exist.
     *
     * @param channel The exact meeting word the desktop opened (includes UUID suffix).
     */
    public void handleStat(String channel) throws Exception {
        Log.d(TAG, "handleStat: starting on " + channel);
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        VDriveEntry entry = dataSource.stat(req.getString("path"));

                        Log.d(TAG, "handleStat: entry=" + entry);

                        if (entry == null) {
                            return new JSONObject().put("ok", false).toString();
                        }

                        // Inline the entry fields at the top level per Protocol.h spec.
                        JSONObject resp = entry.toJson();
                        resp.put("ok", true);
                        return resp.toString();
                    } catch (Exception e) {
                        Log.e(TAG, "handleStat error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── create ────────────────────────────────────────────────────────────────

    /**
     * Serves a {@code virtual_drive_create_{uuid8}} request.
     *
     * <p>PC sends {@code {"path": "...", "is_dir": bool}}.
     * Android responds with {@code {"ok": true}} or {@code {"ok": false, "error": "..."}}.
     *
     * @param channel The exact meeting word the desktop opened (includes UUID suffix).
     */
    public void handleCreate(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        String path = req.getString("path");
                        boolean isDir = req.optBoolean("is_dir", false);
                        dataSource.create(path, isDir);
                        return okJson();
                    } catch (Exception e) {
                        Log.e(TAG, "handleCreate error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── delete ────────────────────────────────────────────────────────────────

    /**
     * Serves a {@code virtual_drive_delete_{uuid8}} request.
     *
     * <p>PC sends {@code {"path": "..."}}.
     *
     * @param channel The exact meeting word the desktop opened (includes UUID suffix).
     */
    public void handleDelete(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        dataSource.delete(req.getString("path"));
                        return okJson();
                    } catch (Exception e) {
                        Log.e(TAG, "handleDelete error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── rename ────────────────────────────────────────────────────────────────

    /**
     * Serves a {@code virtual_drive_rename_{uuid8}} request.
     *
     * <p>PC sends {@code {"from": "...", "to": "..."}}.
     *
     * @param channel The exact meeting word the desktop opened (includes UUID suffix).
     */
    public void handleRename(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        dataSource.rename(req.getString("from"), req.getString("to"));
                        return okJson();
                    } catch (Exception e) {
                        Log.e(TAG, "handleRename error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── truncate ──────────────────────────────────────────────────────────────

    /**
     * Serves a {@code virtual_drive_truncate_{uuid8}} request.
     *
     * <p>PC sends {@code {"path": "...", "new_size": N}}.
     *
     * @param channel The exact meeting word the desktop opened (includes UUID suffix).
     */
    public void handleTruncate(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        dataSource.truncate(req.getString("path"), req.getLong("new_size"));
                        return okJson();
                    } catch (Exception e) {
                        Log.e(TAG, "handleTruncate error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── read ──────────────────────────────────────────────────────────────────

    /**
     * Serves a {@code virtual_drive_read_{uuid8}} request.
     *
     * <h3>Protocol</h3>
     * <p>PC opens {@code virtual_drive_read_{uuid8}}, writes
     * {@code {"path","offset","length"}\n}, then calls {@code read_all()} to consume the
     * file bytes.  Android reads the JSON request, opens the requested file range via
     * {@link VirtualDriveDataSource#openReadRange}, and streams the bytes back on the
     * same channel.  The channel closes (sending FIN) when the {@code InputStream} is
     * exhausted, which unblocks the desktop's {@code read_all()}.
     *
     * <p>No separate negotiation phase or UUID in the payload — the UUID is the channel
     * name suffix itself.  No background thread is spawned; streaming is inline.
     *
     * @param channel The exact meeting word the desktop opened (e.g.
     *                {@code "virtual_drive_read_a1b2c3d4"}).
     */
    public void handleRead(String channel) throws Exception {
        transportManager.serveJsonThenStreamOut(channel, jsonRequest -> {
            JSONObject req = new JSONObject(jsonRequest);
            String path   = req.getString("path");
            long   offset = req.getLong("offset");
            int    length = req.getInt("length");
            Log.d(TAG, "handleRead: path=" + path
                    + " offset=" + offset + " length=" + length + " ch=" + channel);
            return dataSource.openReadRange(path, offset, length);
        });
    }

    // ── write ─────────────────────────────────────────────────────────────────

    /**
     * Serves a {@code virtual_drive_write_{uuid8}} write session.
     *
     * <h3>Protocol</h3>
     * <p>PC opens {@code virtual_drive_write_{uuid8}}, writes {@code {"path"}\n} as a
     * header, then streams the file bytes across one or more internal {@code write} pipe
     * operations, and finally closes the stream on {@code write_close}.  Android reads
     * the path from the header, opens a temp file via
     * {@link VirtualDriveDataSource#openWriteTemp}, and receives all bytes until EOF.
     * After {@link TransportManager#serveJsonHeaderThenStreamIn} returns (temp
     * {@link java.io.FileOutputStream} already closed), Android calls
     * {@link VirtualDriveDataSource#finalizeWrite} to atomically rename temp → final.
     *
     * <p>No separate negotiation phase or UUID in the payload — the UUID is the channel
     * name suffix itself.  No background thread is spawned; streaming is inline.
     *
     * @param channel The exact meeting word the desktop opened (e.g.
     *                {@code "virtual_drive_write_a1b2c3d4"}).
     */
    public void handleWrite(String channel) throws Exception {
        // Capture the path from the JSON header so we can call finalizeWrite after streaming.
        final String[] capturedPath = {null};

        transportManager.serveJsonHeaderThenStreamIn(channel, jsonHeader -> {
            JSONObject req = new JSONObject(jsonHeader);
            String path = req.getString("path");
            capturedPath[0] = path;
            Log.d(TAG, "handleWrite: path=" + path + " ch=" + channel);
            return dataSource.openWriteTemp(path);
        });

        // serveJsonHeaderThenStreamIn has closed the temp OutputStream — safe to rename.
        if (capturedPath[0] != null) {
            dataSource.finalizeWrite(capturedPath[0]);
            Log.d(TAG, "handleWrite: finalized " + capturedPath[0] + " ← " + channel);
        }
    }

    // ── list_page ─────────────────────────────────────────────────────────────

    /**
     * Serves a {@code virtual_drive_list_page_{uuid8}} paginated-listing request.
     *
     * <h3>Protocol</h3>
     * <p>PC sends:
     * <pre>{"path": "...", "after": "last_name_or_null", "limit": N}</pre>
     * Android responds with:
     * <pre>{"ok": true, "entries": [...], "has_more": bool, "next_after": "name_or_null"}</pre>
     * Entries are sorted alphabetically by name.  Pass the returned
     * {@code next_after} value as {@code after} on the next call to advance the
     * cursor.  When {@code has_more} is {@code false} the directory is exhausted.
     *
     * @param channel The exact meeting word the desktop opened (includes UUID suffix).
     */
    public void handleListPage(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req      = new JSONObject(requestJson);
                        String     path     = req.getString("path");
                        String     after    = req.isNull("after") ? null : req.optString("after", null);
                        int        limit    = req.optInt("limit", 200);

                        VirtualDriveDataSource.ListPageResult result =
                                dataSource.listDirPage(path, after, limit);

                        JSONArray arr = new JSONArray();
                        for (VDriveEntry e : result.entries) {
                            arr.put(e.toJson());
                        }
                        JSONObject resp = new JSONObject();
                        resp.put("ok",         true);
                        resp.put("entries",    arr);
                        resp.put("has_more",   result.hasMore);
                        resp.put("next_after", result.nextAfter != null
                                ? result.nextAfter
                                : JSONObject.NULL);
                        return resp.toString();
                    } catch (Exception e) {
                        Log.e(TAG, "handleListPage error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── Private JSON helpers ──────────────────────────────────────────────────

    private static String okJson() {
        try {
            return new JSONObject().put("ok", true).toString();
        } catch (Exception e) {
            return "{\"ok\":true}";
        }
    }

    private static String errorJson(Exception e) {
        try {
            return new JSONObject()
                    .put("ok", false)
                    .put("error", e.getMessage() != null ? e.getMessage() : e.getClass().getSimpleName())
                    .toString();
        } catch (Exception ignored) {
            return "{\"ok\":false}";
        }
    }
}

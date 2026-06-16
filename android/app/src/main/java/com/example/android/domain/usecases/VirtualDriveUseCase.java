package com.example.android.domain.usecases;

import android.util.Log;

import com.example.android.data.datasource.VirtualDriveDataSource;
import com.example.android.domain.entities.VDriveEntry;
import com.example.android.enums.VirtualDriveChannels;
import com.example.android.network.transport.TransportManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.List;

/**
 * Coordinates all virtual-drive operations between the TauSync transport layer
 * and the local file system.
 *
 * <p>Each public method handles one WinFsp operation forwarded by the desktop's
 * {@code VirtualDriveService}:
 * <ul>
 *   <li>Simple ops ({@code list}, {@code stat}, {@code create}, {@code delete},
 *       {@code rename}, {@code truncate}) use a single
 *       {@link TransportManager#serveJsonExchange} call — the entire request/
 *       response round-trip happens on one TauSyncStream.
 *   <li>Two-phase ops ({@code read}, {@code write}) negotiate a UUID on a base
 *       channel then spawn a dedicated background thread that streams bytes on
 *       a UUID-suffixed data channel, keeping the
 *       {@code PeerRequestHandlerThread} free for the next operation.
 * </ul>
 *
 * <p>All methods must be called from a background thread (they block briefly
 * on network I/O for the negotiation phase).  Data-phase threads are named
 * {@code VDriveRead-<uuid>} / {@code VDriveWrite-<uuid>} for easy logcat
 * identification.
 *
 * <p>Threading contract for two-phase ops: the data thread is spawned
 * <em>inside</em> the {@link TransportManager.JsonExchangeHandler} callback —
 * before the ack string is returned.  This guarantees the data thread is
 * already blocking on {@code connect(dataChannel)} by the time the PC exits
 * its own Phase 1 and starts Phase 2, eliminating any race on the data channel.
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
     * Serves a {@code virtual_drive_list} request.
     *
     * <p>PC sends {@code {"path": "..."}}.  Android responds with:
     * <pre>{"ok": true, "entries": [{"name","is_dir","size","mtime_ms"}, ...]}</pre>
     * or {@code {"ok": false, "error": "..."}} on failure.
     */
    public void handleList() throws Exception {
        transportManager.serveJsonExchange(
                VirtualDriveChannels.VIRTUAL_DRIVE_LIST.getValue(),
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
     * Serves a {@code virtual_drive_stat} request.
     *
     * <p>PC sends {@code {"path": "..."}}.  Android responds with the entry's
     * fields inlined at the top level ({@code {"ok":true,"name","is_dir","size","mtime_ms"}})
     * or {@code {"ok": false}} if the path does not exist.
     */
    public void handleStat() throws Exception {
        Log.d(TAG, "handleStat: starting");
        transportManager.serveJsonExchange(
                VirtualDriveChannels.VIRTUAL_DRIVE_STAT.getValue(),
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
     * Serves a {@code virtual_drive_create} request.
     *
     * <p>PC sends {@code {"path": "...", "is_dir": bool}}.
     * Android responds with {@code {"ok": true}} or {@code {"ok": false, "error": "..."}}.
     */
    public void handleCreate() throws Exception {
        transportManager.serveJsonExchange(
                VirtualDriveChannels.VIRTUAL_DRIVE_CREATE.getValue(),
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
     * Serves a {@code virtual_drive_delete} request.
     *
     * <p>PC sends {@code {"path": "..."}}.
     */
    public void handleDelete() throws Exception {
        transportManager.serveJsonExchange(
                VirtualDriveChannels.VIRTUAL_DRIVE_DELETE.getValue(),
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
     * Serves a {@code virtual_drive_rename} request.
     *
     * <p>PC sends {@code {"from": "...", "to": "..."}}.
     */
    public void handleRename() throws Exception {
        transportManager.serveJsonExchange(
                VirtualDriveChannels.VIRTUAL_DRIVE_RENAME.getValue(),
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
     * Serves a {@code virtual_drive_truncate} request.
     *
     * <p>PC sends {@code {"path": "...", "new_size": N}}.
     */
    public void handleTruncate() throws Exception {
        transportManager.serveJsonExchange(
                VirtualDriveChannels.VIRTUAL_DRIVE_TRUNCATE.getValue(),
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

    // ── read (two-phase) ──────────────────────────────────────────────────────

    /**
     * Serves a {@code virtual_drive_read} negotiation and its data phase.
     *
     * <h3>Protocol</h3>
     * <ol>
     *   <li><b>Phase 1</b> — negotiation on {@code virtual_drive_read}:
     *       PC sends {@code {"path","offset","length","uuid"}}; Android spawns the
     *       data thread, then returns {@code {"ok":true}} as the ack.
     *   <li><b>Phase 2</b> — data on {@code virtual_drive_read_{uuid}}:
     *       data thread calls
     *       {@link TransportManager#streamInputStreamToChannel(String, InputStream)}
     *       which streams the requested file range until the stream is closed.
     * </ol>
     *
     * <p>The data thread is spawned <em>before</em> the ack is written so it is
     * already blocking on {@code connect("virtual_drive_read_{uuid}")} when the
     * PC begins Phase 2 — no race condition.
     */
    public void handleRead() throws Exception {
        // Capture fields from Phase 1 JSON so the data thread can reference them.
        final String[] capturedPath = {null};
        final long[] capturedOffset = {0L};
        final int[] capturedLength = {0};
        final String[] capturedUuid = {null};

        transportManager.serveJsonExchange(
                VirtualDriveChannels.VIRTUAL_DRIVE_READ.getValue(),
                requestJson -> {
                    JSONObject req = new JSONObject(requestJson);
                    capturedPath[0] = req.getString("path");
                    capturedOffset[0] = req.getLong("offset");
                    capturedLength[0] = req.getInt("length");
                    capturedUuid[0] = req.getString("uuid");

                    // Spawn data thread BEFORE returning the ack — the thread will
                    // call connect(dataChannel) which may block until PC starts Phase 2.
                    final String path = capturedPath[0];
                    final long offset = capturedOffset[0];
                    final int length = capturedLength[0];
                    final String uuid = capturedUuid[0];
                    final String dataCh = VirtualDriveChannels.VIRTUAL_DRIVE_READ.getValue()
                            + "_" + uuid;

                    new Thread(() -> {
                        try (InputStream is = dataSource.openReadRange(path, offset, length)) {
                            transportManager.streamInputStreamToChannel(dataCh, is);
                            Log.d(TAG, "read data sent: " + path
                                    + " [" + offset + "+" + length + "] → " + dataCh);
                        } catch (Exception e) {
                            Log.e(TAG, "read data thread error [" + dataCh + "]: "
                                    + e.getMessage());
                            // Channel close (stream goes out of scope on exception) sends
                            // FIN to the PC — it will surface as an IO error in WinFsp.
                        }
                    }, "VDriveRead-" + uuid).start();

                    // Ack triggers PC to exit Phase 1 and open the data channel.
                    return okJson();
                }
        );
    }

    // ── write (two-phase) ─────────────────────────────────────────────────────

    /**
     * Serves a {@code virtual_drive_write} negotiation and its data phase.
     *
     * <h3>Protocol</h3>
     * <ol>
     *   <li><b>Phase 1</b> — negotiation on {@code virtual_drive_write}:
     *       PC sends {@code {"path","uuid"}}; Android spawns the data thread, then
     *       returns {@code {"ok":true}} as the ack.
     *   <li><b>Phase 2</b> — data on {@code virtual_drive_write_{uuid}}:
     *       PC holds the stream open and pushes chunks (forwarded from
     *       VirtualDrive.exe write ops via the named pipe).  Android's data thread
     *       calls {@link TransportManager#streamChannelToOutputStream} which
     *       blocks reading until the PC closes the stream on {@code write_close}.
     *       Android then renames the temp file to the final path.
     * </ol>
     */
    public void handleWrite() throws Exception {
        final String[] capturedPath = {null};
        final String[] capturedUuid = {null};

        transportManager.serveJsonExchange(
                VirtualDriveChannels.VIRTUAL_DRIVE_WRITE.getValue(),
                requestJson -> {
                    JSONObject req = new JSONObject(requestJson);
                    capturedPath[0] = req.getString("path");
                    capturedUuid[0] = req.getString("uuid");

                    final String path = capturedPath[0];
                    final String uuid = capturedUuid[0];
                    final String dataCh = VirtualDriveChannels.VIRTUAL_DRIVE_WRITE.getValue()
                            + "_" + uuid;

                    new Thread(() -> {
                        FileOutputStream fos = null;
                        try {
                            fos = dataSource.openWriteTemp(path);
                            // Block until PC closes the data channel (write_close).
                            transportManager.streamChannelToOutputStream(dataCh, fos);
                            fos.close();
                            fos = null;
                            // Atomically publish the file.
                            dataSource.finalizeWrite(path);
                            Log.d(TAG, "write data received: " + path + " ← " + dataCh);
                        } catch (Exception e) {
                            Log.e(TAG, "write data thread error [" + dataCh + "]: "
                                    + e.getMessage());
                        } finally {
                            if (fos != null) {
                                try {
                                    fos.close();
                                } catch (Exception ignored) {
                                }
                            }
                        }
                    }, "VDriveWrite-" + uuid).start();

                    return okJson();
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

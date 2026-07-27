package com.example.android.domain.usecases;

import android.system.ErrnoException;
import android.system.OsConstants;
import android.util.Log;

import com.example.android.domain.entities.VDriveEntry;
import com.example.android.domain.entities.VDrivePageResult;
import com.example.android.domain.entities.VDriveReadRange;
import com.example.android.domain.exceptions.VDriveException;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.VirtualDriveRepository;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.util.List;

/**
 * Handles all WinFsp ops forwarded by the desktop over TauSync.
 * Simple ops (list/stat/create/delete/rename/truncate): serveJsonExchange.
 * Read: serveReadSession — PC opens the channel once sending {path}, then issues
 *   many {offset,length} reads over the same stream until it closes the channel.
 * Write: serveJsonHeaderThenStreamIn — PC sends {path} header then bytes; Android finalizeWrite after.
 * All methods block on I/O — call from a background thread.
 */
public class VirtualDriveUseCase {

    private static final String TAG = "VirtualDriveUC";

    private final TransportManager transportManager;
    private final VirtualDriveRepository repository;

    public VirtualDriveUseCase(TransportManager transportManager,
                               VirtualDriveRepository repository) {
        this.transportManager = transportManager;
        this.repository = repository;
    }

    // ── list ──────────────────────────────────────────────────────────────────

    // PC sends {"path"}; responds with {"ok":true,"entries":[...]}
    public void handleList(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        String path = req.getString("path");
                        List<VDriveEntry> entries = repository.listDir(path);

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

    // PC sends {"path"}; responds with entry fields inlined, or {"ok":false} if missing
    public void handleStat(String channel) throws Exception {
        Log.d(TAG, "handleStat: starting on " + channel);
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        VDriveEntry entry = repository.stat(req.getString("path"));

                        Log.d(TAG, "handleStat: entry=" + entry);

                        if (entry == null) {
                            // null = genuinely missing (restricted roots are short-circuited
                            // in the DataSource and never reach here as null). Do NOT
                            // synthesize a directory — desktop.ini would look like a folder
                            // and break Explorer navigation.
                            return new JSONObject().put("ok", false).toString();
                        }

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

    // PC sends {"path","is_dir"}; responds with {"ok":true} or {"ok":false,"error":"..."}
    public void handleCreate(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        String path = req.getString("path");
                        boolean isDir = req.optBoolean("is_dir", false);
                        repository.create(path, isDir);
                        return okJson();
                    } catch (Exception e) {
                        Log.e(TAG, "handleCreate error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── delete ────────────────────────────────────────────────────────────────

    // PC sends {"path"}
    public void handleDelete(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        repository.delete(req.getString("path"));
                        return okJson();
                    } catch (Exception e) {
                        Log.e(TAG, "handleDelete error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── rename ────────────────────────────────────────────────────────────────

    // PC sends {"from","to"}
    public void handleRename(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        repository.rename(req.getString("from"), req.getString("to"));
                        return okJson();
                    } catch (Exception e) {
                        Log.e(TAG, "handleRename error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── truncate ──────────────────────────────────────────────────────────────

    // PC sends {"path","new_size"}
    public void handleTruncate(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        repository.truncate(req.getString("path"), req.getLong("new_size"));
                        return okJson();
                    } catch (Exception e) {
                        Log.e(TAG, "handleTruncate error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── read ──────────────────────────────────────────────────────────────────

    // Persistent read session: PC opens the channel once sending {"path"}, then
    // issues many {"offset","length"} reads against that one file over the same
    // stream until it closes the channel. Reusing the channel keeps video playback
    // smooth — no per-read TauSync handshake or channel churn.
    public void handleRead(String channel) throws Exception {
        transportManager.serveReadSession(channel, (path, offset, length) -> {
            Log.d(TAG, "handleRead: path=" + path
                    + " offset=" + offset + " length=" + length + " ch=" + channel);
            try {
                VDriveReadRange range =
                        repository.openReadRangeChecked(path, offset, length);
                return TransportManager.ReadResult.ok(range.available, range.stream);
            } catch (FileNotFoundException e) {
                // distinguish statable-but-unreadable (Android/data) from truly missing
                String code = repository.exists(path) ? "access_denied" : "not_found";
                Log.w(TAG, "handleRead: open failed (" + code + ") for " + path, e);
                return TransportManager.ReadResult.error(code);
            } catch (SecurityException | IOException e) {
                String code = toErrorCode(e);
                Log.w(TAG, "handleRead: " + code + " for " + path, e);
                return TransportManager.ReadResult.error(code);
            }
        });
    }

    // ── write ─────────────────────────────────────────────────────────────────

    // PC sends {"path"} header then streams bytes; Android writes to temp file, then finalizes
    public void handleWrite(String channel) throws Exception {
        final String[] capturedPath = {null};

        transportManager.serveJsonHeaderThenStreamIn(channel, jsonHeader -> {
            JSONObject req = new JSONObject(jsonHeader);
            String path = req.getString("path");
            capturedPath[0] = path;
            Log.d(TAG, "handleWrite: path=" + path + " ch=" + channel);
            return repository.openWriteTemp(path);
        });

        // temp OutputStream is closed by serveJsonHeaderThenStreamIn — safe to rename now
        if (capturedPath[0] != null) {
            repository.finalizeWrite(capturedPath[0]);
            Log.d(TAG, "handleWrite: finalized " + capturedPath[0] + " ← " + channel);
        }
    }

    // ── list_page ─────────────────────────────────────────────────────────────

    // PC sends {"path","after","limit"}; responds with {"ok","entries","has_more","next_after"}
    public void handleListPage(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req   = new JSONObject(requestJson);
                        String     path  = req.getString("path");
                        String     after = req.isNull("after") ? null : req.optString("after", null);
                        int        limit = req.optInt("limit", 200);

                        VDrivePageResult result = repository.listDirPage(path, after, limit);

                        JSONArray arr = new JSONArray();
                        for (VDriveEntry e : result.entries) {
                            arr.put(e.toJson());
                        }
                        JSONObject resp = new JSONObject();
                        resp.put("ok",       true);
                        resp.put("entries",  arr);
                        resp.put("has_more", result.hasMore);
                        // must be "" not null — nlohmann j.value("next_after","") throws
                        // type_error.302 on a present-but-null field and tears the drive down
                        resp.put("next_after", result.nextAfter != null ? result.nextAfter : "");
                        return resp.toString();
                    } catch (Exception e) {
                        Log.e(TAG, "handleListPage error: " + e.getMessage());
                        return errorJson(e);
                    }
                }
        );
    }

    // ── list_full ─────────────────────────────────────────────────────────────

    // PC sends {"path"}; responds with {"ok","dir_mtime_ms","entries"} — full dir in one shot
    // Desktop caches the listing under a short TTL and serves every list_page request of one
    // enumeration locally, so a folder costs one round-trip instead of one per page.
    // dir_mtime_ms is reported for diagnostics; the desktop does not revalidate against it
    // (it arrives with the listing, and a dir's mtime is unchanged by an in-place child write).
    public void handleListFull(String channel) throws Exception {
        transportManager.serveJsonExchange(
                channel,
                requestJson -> {
                    try {
                        JSONObject req = new JSONObject(requestJson);
                        String path = req.getString("path");

                        // dir mtime is the cache validity token — changes when children change
                        VDriveEntry dir = repository.stat(path);
                        long dirMtimeMs = dir != null ? dir.getMtimeMs() : 0L;

                        List<VDriveEntry> entries = repository.listDir(path);
                        JSONArray arr = new JSONArray();
                        for (VDriveEntry e : entries) {
                            arr.put(e.toJson());
                        }
                        JSONObject resp = new JSONObject();
                        resp.put("ok",           true);
                        resp.put("dir_mtime_ms", dirMtimeMs);
                        resp.put("entries",      arr);
                        return resp.toString();
                    } catch (Exception e) {
                        Log.e(TAG, "handleListFull error: " + e.getMessage());
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
                    .put("error", toErrorCode(e))
                    .put("detail", e.getMessage() != null ? e.getMessage() : e.getClass().getSimpleName())
                    .toString();
        } catch (Exception ignored) {
            return "{\"ok\":false,\"error\":\"io_error\"}";
        }
    }

    /**
     * Reduces an exception to one of the stable codes the desktop understands.
     *
     * <p>{@code VirtualDrive::ErrorToStatus} on the Windows side matches on a
     * fixed vocabulary to pick an NTSTATUS; anything outside it collapses to
     * {@code STATUS_IO_DEVICE_ERROR}, which Explorer reports as a device fault no
     * matter what actually went wrong. Raw {@code e.getMessage()} text — for
     * instance the kernel's "Operation not permitted" — always fell into that
     * bucket, so a missing permission looked identical to failing hardware. The
     * original message still travels in the response's {@code detail} field.
     */
    static String toErrorCode(Exception e) {
        if (e instanceof VDriveException) {
            return ((VDriveException) e).getCode();
        }
        if (e instanceof SecurityException) {
            return "access_denied";
        }
        if (e instanceof FileNotFoundException) {
            return "not_found";
        }
        if (e instanceof ErrnoException) {
            return errnoToCode(((ErrnoException) e).errno);
        }

        // Some File-API failures surface the errno only as strerror text.
        String message = e.getMessage();
        if (message != null) {
            if (message.contains("Operation not permitted")
                    || message.contains("Permission denied")
                    || message.contains("EPERM")
                    || message.contains("EACCES")) {
                return "access_denied";
            }
            if (message.contains("No such file or directory")) {
                return "not_found";
            }
        }
        return "io_error";
    }

    private static String errnoToCode(int errno) {
        if (errno == OsConstants.EPERM || errno == OsConstants.EACCES) return "access_denied";
        if (errno == OsConstants.ENOENT)                               return "not_found";
        if (errno == OsConstants.ENOTDIR)                              return "not_dir";
        if (errno == OsConstants.EEXIST)                               return "exists";
        if (errno == OsConstants.ENOTEMPTY)                            return "not_empty";
        return "io_error";
    }
}

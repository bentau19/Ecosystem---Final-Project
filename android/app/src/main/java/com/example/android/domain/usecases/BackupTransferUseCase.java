package com.example.android.domain.usecases;

import android.content.ContentResolver;
import android.content.Context;
import android.net.Uri;
import android.util.Log;

import com.example.android.domain.entities.BackupFileEntry;
import com.example.android.enums.BackupChannels;
import com.example.android.enums.FileTransferResponse;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.BackupRepository;

import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Sends a list of backup files from Android to the connected PC, one file at a time.
 *
 * <p>Must be called from a background thread — all operations are synchronous network I/O.
 *
 * <p>This use case is the backbone of the backup transfer phase and mirrors
 * {@link SendFileUseCase} in structure but:
 * <ul>
 *   <li>Uses {@link BackupChannels} (not {@link com.example.android.enums.FileTransferChannels})
 *       to avoid colliding with share-sheet single-file transfers.</li>
 *   <li>Iterates over a {@code List<BackupFileEntry>} rather than a single URI.</li>
 *   <li>Reports incremental per-file progress via {@link BackupRepository}.</li>
 * </ul>
 *
 * <p>Per-file protocol (mirrors {@link SendFileUseCase}):
 * <ol>
 *   <li>Build JSON metadata from {@link BackupFileEntry} fields and send it on
 *       {@link BackupChannels#METADATA_ANDROID_TO_PC}.</li>
 *   <li>Wait up to {@link #RESPONSE_TIMEOUT_SECONDS} for PC's Accept / Reject on
 *       {@link BackupChannels#RESPONSE_FROM_PC}.
 *       Timeout → abort the entire batch with FAILED.</li>
 *   <li>If accepted: open an {@link InputStream} from
 *       {@link BackupFileEntry#getSourceUri()} and stream bytes on
 *       {@link BackupChannels#DATA_ANDROID_TO_PC}.</li>
 *   <li>If rejected: skip this file and continue with the next one.</li>
 *   <li>After each accepted file: call {@link BackupRepository#onFileTransferred(int, int)}
 *       so the progress notification and in-app counter stay in sync.</li>
 * </ol>
 */
public class BackupTransferUseCase {

    private static final String TAG = "BackupTransferUseCase";

    /**
     * Seconds the PC has to respond to each file's metadata before we give up.
     * Long enough for the PC user to notice the dialog; short enough that a
     * disconnected desktop doesn't stall the phone forever.
     */
    private static final int RESPONSE_TIMEOUT_SECONDS = 60;

    private final TransportManager transportManager;
    private final BackupRepository repository;
    private final Context context;

    public BackupTransferUseCase(TransportManager transportManager,
                                 BackupRepository repository,
                                 Context context) {
        this.transportManager = transportManager;
        this.repository       = repository;
        this.context          = context.getApplicationContext();
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Executes the full backup transfer for the given file list.
     *
     * <p>Must be called from a background thread (spawned by {@code ConnectivityService}).
     * Progress is reported back to {@link BackupRepository} via
     * {@link BackupRepository#onFileTransferred}, which in turn drives the
     * sticky progress notification via LiveData.
     *
     * @param files Non-null, non-empty list produced by
     *              {@link ScanBackupFilesUseCase}.
     */
    public void execute(List<BackupFileEntry> files) {
        if (files == null || files.isEmpty()) {
            Log.w(TAG, "execute called with empty file list — nothing to send");
            repository.onTransferComplete();
            return;
        }

        final int total = files.size();
        int sent = 0;

        Log.d(TAG, "execute: starting backup transfer — " + total + " files");

        for (BackupFileEntry entry : files) {
            if (!transportManager.isConnected()) {
                Log.e(TAG, "Transport disconnected mid-backup — aborting");
                repository.onTransferFailed();
                return;
            }

            try {
                boolean accepted = sendSingleFile(entry);
                if (accepted) {
                    sent++;
                    // Post progress for this file; total is known for the whole batch.
                    repository.onFileTransferred(sent, total);
                    Log.d(TAG, "File " + sent + "/" + total + " sent: " + entry.getDisplayPath());
                } else {
                    Log.d(TAG, "File skipped (PC rejected): " + entry.getDisplayPath());
                }
            } catch (Exception e) {
                Log.e(TAG, "Transfer failed on file: " + entry.getDisplayPath()
                        + " — " + e.getMessage());
                repository.onTransferFailed();
                return;
            }
        }

        Log.d(TAG, "execute: backup transfer complete — " + sent + "/" + total + " files accepted");
        repository.onTransferComplete();
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    /**
     * Sends a single file through the three-step backup protocol.
     *
     * @param entry File to send.
     * @return {@code true} if the PC accepted and bytes were streamed;
     *         {@code false} if the PC rejected (caller should skip the file).
     * @throws Exception on network error, timeout, or I/O failure.
     */
    private boolean sendSingleFile(BackupFileEntry entry) throws Exception {
        // ── Step 1: Build & send JSON metadata ───────────────────────────────
        JSONObject json = new JSONObject();
        json.put("file_name",   entry.getDisplayPath()
                .contains("/")
                ? entry.getDisplayPath().substring(entry.getDisplayPath().lastIndexOf('/') + 1)
                : entry.getDisplayPath());
        json.put("file_size",   entry.getSizeBytes());
        json.put("modified_at", entry.getMtimeMs());
        String metadataPayload = json.toString();

        Log.d(TAG, "Sending metadata: " + metadataPayload);
        transportManager.writeToChannel(
                BackupChannels.METADATA_ANDROID_TO_PC.getValue(),
                metadataPayload
        );

        // ── Step 2: Wait for PC's Accept / Reject ─────────────────────────────
        Log.d(TAG, "Waiting for PC response for: " + entry.getDisplayPath());
        String response = readWithTimeout(
                BackupChannels.RESPONSE_FROM_PC.getValue(),
                RESPONSE_TIMEOUT_SECONDS
        );

        if (FileTransferResponse.REJECTED_FROM_PC.getValue().equals(response)) {
            Log.d(TAG, "PC rejected file: " + entry.getDisplayPath());
            return false;
        }

        if (!FileTransferResponse.ACCEPTED_FROM_PC.getValue().equals(response)) {
            throw new IOException("Unexpected response token from PC: \"" + response + "\"");
        }

        // ── Step 3: Stream bytes ──────────────────────────────────────────────
        Uri sourceUri = Uri.parse(entry.getSourceUri());
        ContentResolver resolver = context.getContentResolver();

        try (InputStream inputStream = resolver.openInputStream(sourceUri)) {
            if (inputStream == null) {
                throw new IOException("Failed to open InputStream for: " + entry.getDisplayPath());
            }
            transportManager.streamInputStreamToChannel(
                    BackupChannels.DATA_ANDROID_TO_PC.getValue(),
                    inputStream
            );
        }

        return true;
    }

    /**
     * Reads a string from {@code channel} with a hard timeout.
     *
     * <p>Mirrors the same helper in {@link SendFileUseCase} — if the PC user
     * ignores the backup-accept dialog, we fail after {@code timeoutSeconds}
     * instead of blocking forever.
     */
    private String readWithTimeout(String channel, int timeoutSeconds) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        Future<String> future = executor.submit(() ->
                transportManager.readFromChannel(channel)
        );
        try {
            return future.get(timeoutSeconds, TimeUnit.SECONDS);
        } catch (TimeoutException e) {
            future.cancel(true);
            throw new Exception(
                    "PC did not respond within " + timeoutSeconds
                            + " seconds — backup transfer timed out");
        } finally {
            executor.shutdownNow();
        }
    }
}

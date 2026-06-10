package com.example.android.domain.usecases;

import android.content.ContentResolver;
import android.content.Context;
import android.net.Uri;
import android.util.Log;

import com.example.android.data.datasource.BackupDataSource;
import com.example.android.domain.entities.BackupFileEntry;
import com.example.android.domain.entities.BackupOptions;
import com.example.android.enums.BackupChannels;
import com.example.android.network.handlers.BackupReceivedChannelHandler;
import com.example.android.network.handlers.ChannelHandlerRegistry;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.BackupRepository;

import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Sends a batch of backup files from Android to the connected PC.
 *
 * <p>Protocol (3 steps):
 * <ol>
 *   <li><b>Manifest</b> — writes {@code {file_count, files_bytes, classify}} on
 *       {@link BackupChannels#BACKUP_MANIFEST_FROM_ANDROID} so the PC can show
 *       "N files / X bytes" in its folder-picker dialog and know whether to run
 *       content classification.</li>
 *   <li><b>Ready</b> — waits up to {@link #READY_TIMEOUT_SECONDS} for the PC's ack on
 *       {@link BackupChannels#BACKUP_READY_FROM_PC}.  Aborts with
 *       {@link BackupRepository#onTransferFailed()} on timeout or empty response.</li>
 *   <li><b>Slots</b> — opens up to {@code options.getParallelSlots()} file slot channels
 *       concurrently using a fixed-size thread pool.  Each slot writes a newline-terminated
 *       JSON header ({@code {"name": "photo.jpg", "size": N}\n}) followed by the raw file
 *       bytes on {@code "backup_slot_" + i}.  Slot threads are responsible only for
 *       streaming bytes; they do <em>not</em> read per-file results.
 *       <p>Per-file results ({@code "backup_file_result_{i}"}) are received by a
 *       {@link BackupReceivedChannelHandler} registered in the
 *       {@link ChannelHandlerRegistry} for the duration of this transfer. The handler
 *       fires for each result channel the PC opens (detected by the 2-second polling
 *       loop), calls {@link BackupRepository#onFileTransferred} and
 *       {@link BackupRepository#onFileResult}, optionally deletes the source file, and
 *       counts down a shared {@link CountDownLatch}. This UseCase polls that latch
 *       (500 ms ticks) until all results arrive and then calls
 *       {@link BackupRepository#onTransferComplete()}.
 *       Progress is therefore still tied to PC confirmation — the only change is
 *       that result reading happens in the handler rather than inside the slot threads.
 *       </li>
 * </ol>
 *
 * <p>Must be called from a background thread (spawned by {@code ConnectivityService}) —
 * all operations are blocking network I/O.
 */
public class BackupTransferUseCase {

    private static final String TAG = "BackupTransferUseCase";

    /**
     * Seconds the PC user has to confirm the destination folder before we abort.
     */
    private static final int READY_TIMEOUT_SECONDS = 120;

    private final TransportManager transportManager;
    private final BackupRepository repository;
    private final Context context;
    private final BackupDataSource backupDataSource;
    private final ChannelHandlerRegistry registry;

    // ── Per-session control flags (reset at the start of every execute()) ─────
    // Promoted to instance fields so public pause/resume/stop methods can reach them.

    /**
     * Set by pauseTransfer(); cleared by resumeTransfer() or stopTransfer().
     */
    private final AtomicBoolean pauseFlag = new AtomicBoolean(false);

    /**
     * Set by stopTransfer(); once set, never cleared in the same session.
     */
    private final AtomicBoolean stopFlag = new AtomicBoolean(false);

    /**
     * Set to true by any first failure or stop.  Guards against calling
     * {@code repository.onTransferFailed/Stopped} more than once per session.
     */
    private final AtomicBoolean aborted = new AtomicBoolean(false);

    public BackupTransferUseCase(TransportManager transportManager,
                                 BackupRepository repository,
                                 Context context,
                                 BackupDataSource backupDataSource,
                                 ChannelHandlerRegistry registry) {
        this.transportManager = transportManager;
        this.repository = repository;
        this.context = context.getApplicationContext();
        this.backupDataSource = backupDataSource;
        this.registry = registry;
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Executes the full backup transfer for the given file list.
     *
     * <p>Must be called from a background thread (spawned by {@code ConnectivityService}).
     * Progress is reported back to {@link BackupRepository} via
     * {@link BackupRepository#onFileTransferred}, which drives the sticky progress
     * notification via LiveData. The counter is only advanced once the PC confirms
     * each file ("pc_finish" — its result on {@code backup_file_result_{slotIndex}}),
     * not as soon as Android finishes streaming the file's bytes.
     *
     * @param files   Non-null, non-empty list produced by {@link ScanBackupFilesUseCase}.
     * @param options User-configured backup options; {@code classify_images} is included
     *                in the manifest so the PC knows whether to run content classification.
     */
    public void execute(List<BackupFileEntry> files, BackupOptions options) {
        if (files == null || files.isEmpty()) {
            Log.w(TAG, "execute: empty file list — nothing to send");
            repository.onTransferComplete();
            return;
        }

        // Reset per-session flags so a re-used UseCase instance starts clean.
        pauseFlag.set(false);
        stopFlag.set(false);
        aborted.set(false);

        final int total = files.size();
        final boolean classify = options != null && options.isClassifyImages();
        Log.d(TAG, "execute: starting backup transfer — " + total + " files"
                + ", classify=" + classify);

        try {
            // ── Step 1: send lightweight manifest ────────────────────────────
            sendManifest(files, classify);

            // ── Step 2: wait for PC ready ─────────────────────────────────────
            Log.d(TAG, "Waiting for PC ready (timeout=" + READY_TIMEOUT_SECONDS + "s)");
            String readyToken = readWithTimeout(
                    BackupChannels.BACKUP_READY_FROM_PC.getValue(), READY_TIMEOUT_SECONDS);
            if (readyToken == null || readyToken.isEmpty()) {
                Log.e(TAG, "PC did not send READY — aborting backup");
                repository.onTransferFailed();
                return;
            }
            Log.d(TAG, "PC ready — beginning slot streams");

            // ── Step 3: per-slot file streams (parallel) ─────────────────────
            final int parallelSlots = (options != null) ? options.getParallelSlots() : 1;
            Log.d(TAG, "Starting parallel transfer — " + total
                    + " files, " + parallelSlots + " concurrent slot(s)");

            // ── Shared synchronisation between streaming threads and result handler ──
            // resultsLatch counts down once per PC-confirmed result (in the handler).
            // confirmedCount is the running progress number forwarded to the repository.
            CountDownLatch resultsLatch   = new CountDownLatch(total);
            AtomicInteger confirmedCount  = new AtomicInteger(0);

            // ── Register the per-file result handler ──────────────────────────
            // BackupReceivedChannelHandler is registered under the prefix
            // "backup_file_result_" and handles "backup_file_result_0",
            // "backup_file_result_1", ... via the registry's prefix-match fallback.
            // It reads each PC result, updates repository state, optionally deletes
            // the source file, and counts down resultsLatch.
            BackupReceivedChannelHandler receivedHandler = new BackupReceivedChannelHandler(
                    transportManager, repository, backupDataSource, context,
                    options, files, total, confirmedCount, aborted, resultsLatch);
            registry.registerHandler(BackupChannels.BACKUP_FILE_RESULT.getValue(), receivedHandler);

            // ── Streaming pool: slot threads only send bytes ──────────────────
            ExecutorService pool = Executors.newFixedThreadPool(parallelSlots);
            CountDownLatch streamLatch = new CountDownLatch(total);

            for (int i = 0; i < total; i++) {
                final int slotIndex = i;
                pool.submit(() -> {
                    try {
                        // ── Stop check ────────────────────────────────────────
                        if (stopFlag.get() || !transportManager.isConnected()) {
                            Log.w(TAG, "Slot " + slotIndex + " skipped — stopped or disconnected");
                            aborted.set(true);
                            return;
                        }

                        // ── Pause check (spin until resumed or stopped) ───────
                        while (pauseFlag.get()) {
                            if (stopFlag.get()) {
                                aborted.set(true);
                                return;
                            }
                            try {
                                Thread.sleep(200);
                            } catch (InterruptedException ie) {
                                Thread.currentThread().interrupt();
                                aborted.set(true);
                                return;
                            }
                        }

                        // Re-check stop after waking from pause
                        if (stopFlag.get()) {
                            aborted.set(true);
                            return;
                        }

                        BackupFileEntry entry = files.get(slotIndex);
                        Log.d(TAG, "Slot " + slotIndex + ": " + entry.getDisplayPath()
                                + " (" + entry.getSizeBytes() + " B)");
                        streamSlot(entry, slotIndex);
                        // Streaming done — BackupReceivedChannelHandler will read
                        // the PC's result on "backup_file_result_{slotIndex}" and
                        // count down resultsLatch once the PC confirms.
                        Log.d(TAG, "Slot " + slotIndex + " streamed — waiting for PC result via handler");

                    } catch (Exception e) {
                        Log.e(TAG, "Slot " + slotIndex + " failed: " + e.getMessage(), e);
                        if (aborted.compareAndSet(false, true)) {
                            repository.onTransferFailed();
                        }
                    } finally {
                        streamLatch.countDown();
                    }
                });
            }

            pool.shutdown();

            // ── Wait for all bytes to finish streaming ────────────────────────
            try {
                streamLatch.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                Log.e(TAG, "Backup transfer interrupted while streaming");
                if (aborted.compareAndSet(false, true)) {
                    repository.onTransferFailed();
                }
                registry.unregisterHandler(BackupChannels.BACKUP_FILE_RESULT.getValue());
                return;
            }

            // ── Abort check after streaming ───────────────────────────────────
            if (aborted.get()) {
                Log.d(TAG, "Transfer aborted after streaming — unregistering result handler");
                registry.unregisterHandler(BackupChannels.BACKUP_FILE_RESULT.getValue());
                return;
            }

            // ── Wait for handler to receive all PC confirmations ──────────────
            // Poll in 500 ms ticks so stop() or a connection drop wakes us promptly
            // without relying on thread interruption.
            Log.d(TAG, "All slots streamed — waiting for " + total + " PC result(s) via handler");
            try {
                while (!aborted.get() && transportManager.isConnected()) {
                    if (resultsLatch.await(500, TimeUnit.MILLISECONDS)) {
                        break;  // all results received
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                Log.e(TAG, "Backup transfer interrupted while waiting for PC results");
                if (aborted.compareAndSet(false, true)) {
                    repository.onTransferFailed();
                }
                registry.unregisterHandler(BackupChannels.BACKUP_FILE_RESULT.getValue());
                return;
            }

            // ── Unregister handler + decide terminal state ────────────────────
            registry.unregisterHandler(BackupChannels.BACKUP_FILE_RESULT.getValue());

            if (!aborted.get()) {
                Log.d(TAG, "Backup transfer complete — " + total + " files confirmed by PC");
                repository.onTransferComplete();
            } else {
                Log.d(TAG, "Backup transfer finished with abort flag — terminal state already posted");
            }

        } catch (Exception e) {
            Log.e(TAG, "Backup transfer failed: " + e.getMessage(), e);
            if (aborted.compareAndSet(false, true)) {
                repository.onTransferFailed();
            }
        }
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    /**
     * Sends the lightweight manifest on
     * {@link BackupChannels#BACKUP_MANIFEST_FROM_ANDROID}.
     *
     * <p>Wire format: {@code {"file_count": N, "files_bytes": S, "classify": true|false}}.
     * The PC uses this to populate its folder-picker dialog with a human-readable
     * summary ("42 files · 1.2 GB") and to decide whether to run image classification
     * on the received files.
     *
     * @param files    The file list whose count and combined size are written.
     * @param classify {@code true} to ask the PC to send per-file classify results;
     *                 {@code false} to skip classification entirely.
     * @throws Exception if the TauSync write fails.
     */
    private void sendManifest(List<BackupFileEntry> files, boolean classify) throws Exception {
        long totalSizeBytes = 0;
        for (BackupFileEntry entry : files) {
            totalSizeBytes += entry.getSizeBytes();
        }

        JSONObject manifest = new JSONObject();
        manifest.put("file_count", files.size());
        manifest.put("files_bytes", totalSizeBytes);
        manifest.put("classify", classify);

        Log.d(TAG, "Sending manifest: " + manifest);
        transportManager.writeToChannel(
                BackupChannels.BACKUP_MANIFEST_FROM_ANDROID.getValue(),
                manifest.toString()
        );
    }

    /**
     * Sends per-file metadata followed by raw bytes on channel
     * {@code "backup_slot_" + slotIndex}, using a single TauSync connect.
     *
     * <p>Wire format:
     * <pre>
     *   {"name": "photo.jpg", "size": N}\n
     *   [raw file bytes — exactly N bytes]
     * </pre>
     *
     * <p>The PC reads up to the first {@code '\n'} to parse the JSON header, then
     * drains exactly {@code N} bytes from the same stream as the file payload.
     * This works because TauSync's {@code read_line()} stores any overflow in an
     * internal buffer that {@code read_to_file()} drains first.
     *
     * <p>Uses try-with-resources to guarantee the InputStream is closed even on error.
     *
     * @param entry     File to send.
     * @param slotIndex Zero-based position of this file in the scan order.
     * @throws Exception if the URI cannot be opened or the channel write fails.
     */
    private void streamSlot(BackupFileEntry entry, int slotIndex) throws Exception {
        String slotChannel = BackupChannels.BACKUP_FILE_SLOT.getValue() + slotIndex;

        // ── Per-file metadata header — must match keys the PC expects ─────────
        // PC code: meta["name"]     → bare filename for display / cache key
        //          meta["rel_path"] → relative path within chosen root (folder mode only)
        //                             desktop uses this to reconstruct directory structure
        //          meta["size"]     → exact byte count to read from the stream
        String fileName = new java.io.File(entry.getDisplayPath()).getName();
        Log.d(TAG, "streamSlot: " + new java.io.File(entry.getDisplayPath()).toString());
        JSONObject meta = new JSONObject();
        meta.put("name", fileName);
        meta.put("size", entry.getSizeBytes());
        meta.put("mtime", entry.getMtimeMs());
        // Include rel_path only when available (MODE_FOLDER); absent in MODE_ALL_MEDIA.
        String relPath = entry.getRelPath();
        if (relPath != null && !relPath.isEmpty()) {
            meta.put("rel_path", relPath);
        }
        String metadataJson = meta.toString(); // compact JSON — no bare '\n' inside

        // ── Single connect: newline-terminated header line + raw bytes ─────────
        Uri sourceUri = Uri.parse(entry.getSourceUri());
        ContentResolver resolver = context.getContentResolver();

        try (InputStream is = resolver.openInputStream(sourceUri)) {
            if (is == null) {
                throw new IOException("Cannot open InputStream for: " + entry.getDisplayPath());
            }
            // writeMetadataThenStreamToChannel writes (metadataJson + "\n") then pipes is
            transportManager.writeMetadataThenStreamToChannel(slotChannel, metadataJson, is);
        }
    }

    /**
     * Reads a string from {@code channel} with a hard timeout.
     *
     * <p>Mirrors the same helper used in {@link SendFileUseCase} — wraps the
     * blocking {@code readFromChannel} in a {@link Future} so we fail-fast instead
     * of blocking forever if the PC user ignores the dialog.
     */
    private String readWithTimeout(String channel, int timeoutSeconds) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        Future<String> future = executor.submit(() ->
                transportManager.readFromChannel(channel));
        try {
            return future.get(timeoutSeconds, TimeUnit.SECONDS);
        } catch (TimeoutException e) {
            future.cancel(true);
            throw new Exception(
                    "Timed out waiting for PC on channel '" + channel
                            + "' after " + timeoutSeconds + "s");
        } finally {
            executor.shutdownNow();
        }
    }

    // ── Public pause / resume / stop (called by ConnectivityService) ──────────

    /**
     * Pauses the transfer after the current in-flight slots finish.
     * Also signals the PC via {@code backup_ctrl_android} so its receiver loop pauses.
     */
    public void pauseTransfer() {
        if (stopFlag.get()) return;
        pauseFlag.set(true);
        repository.onTransferPaused();
        sendControlToPC("pause");
    }

    /**
     * Resumes a paused transfer.
     * Signals the PC so its slot-discovery loop unblocks.
     */
    public void resumeTransfer() {
        if (stopFlag.get()) return;
        pauseFlag.set(false);
        repository.onTransferResumed();
        sendControlToPC("resume");
    }

    /**
     * Stops the transfer immediately (non-resumable).
     * Unblocks any paused slot workers so they can exit cleanly, then signals the PC.
     */
    public void stopTransfer() {
        stopFlag.set(true);
        pauseFlag.set(false); // unblock paused slots so they see stopFlag
        if (aborted.compareAndSet(false, true)) {
            repository.onTransferStopped();
        }
        sendControlToPC("stop");
    }

    /**
     * Fire-and-forget: sends a JSON control command to the PC on
     * {@link BackupChannels#BACKUP_CONTROL_FROM_ANDROID}.
     * Exceptions are swallowed — the command is best-effort.
     */
    private void sendControlToPC(String cmd) {
        new Thread(() -> {
            try {
                org.json.JSONObject payload = new org.json.JSONObject();
                payload.put("cmd", cmd);
                transportManager.writeToChannel(
                        BackupChannels.BACKUP_CONTROL_FROM_ANDROID.getValue(),
                        payload.toString());
                Log.d(TAG, "Control command sent to PC: " + cmd);
            } catch (Exception e) {
                Log.w(TAG, "sendControlToPC '" + cmd + "' failed: " + e.getMessage());
            }
        }, "BackupControlSendThread").start();
    }
}

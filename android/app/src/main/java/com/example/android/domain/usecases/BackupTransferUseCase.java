package com.example.android.domain.usecases;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.util.Log;

import com.example.android.data.datasource.BackupDataSource;
import com.example.android.domain.entities.BackupFileEntry;
import com.example.android.domain.entities.BackupOptions;
import com.example.android.enums.BackupChannels;
import com.example.android.enums.BackupFileResult;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.BackupRepository;

import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;

import com.example.android.utils.VideoTranscoder;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
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
 *       {@link BackupChannels#BACKUP_READY_FROM_PC}. Aborts with
 *       {@link BackupRepository#onTransferFailed()} on timeout or empty response.</li>
 *   <li><b>Slots</b> — opens up to {@link #MAX_PARALLEL_SLOTS} file slot channels
 *       concurrently using a fixed-size thread pool. Each slot:
 *       <ol>
 *         <li>Sends JSON metadata on {@code "backup_slot_meta_" + i}.</li>
 *         <li>Streams raw bytes on {@code "backup_slot_data_" + i}.</li>
 *         <li>Blocks on {@code "backup_file_result_" + i} until the PC confirms
 *             the file (result = "succ" or "fail").</li>
 *       </ol>
 *       This design caps parallel work at {@link #MAX_PARALLEL_SLOTS} full round-trips,
 *       prevents Android from racing ahead of the PC, and eliminates the async
 *       {@code BackupReceivedChannelHandler} / polling-registry approach that was
 *       prone to result-channel race conditions.
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

    /**
     * Hard cap on concurrent file-slot threads, matching the PC's
     * {@code MAX_CONCURRENT_RECEIVES = 5} semaphore so Android never queues more
     * inflight requests than the PC can accept simultaneously.
     */
    private static final int MAX_PARALLEL_SLOTS = 5;

    // ── Data-channel connect-timeout calibration (mirrors desktop backup.py) ──
    // Formula: ceil(DATA_TIMEOUT_MULT * fileSizeBytes) + DATA_TIMEOUT_OFFSET_S
    // Pessimistic floor: 5 MB/s (slow mobile hotspot / congested Wi-Fi).
    // The timeout governs only the TauSync meeting handshake — how long Android
    // waits for the PC to call connect() on the data channel — not the total
    // transfer time. Examples: 10 MB → 32 s | 100 MB → 50 s | 1 GB → 230 s
    private static final double DATA_TIMEOUT_MULT = 1.0 / 3_000_000; // s per byte
    private static final int DATA_TIMEOUT_OFFSET_S = 30;               // baseline seconds

    /**
     * Extra seconds added on top of {@link #dataTimeout(long)} when waiting for the
     * PC's per-file result on {@code "backup_file_result_N"}.
     *
     * <p>After Android finishes streaming, the PC still needs time to:
     * <ul>
     *   <li>Acquire its data semaphore (up to one full download's worth of time)</li>
     *   <li>Read bytes from the TCP buffer</li>
     *   <li>Run ML classification (0–30 s per file)</li>
     *   <li>Copy the file to the destination folder</li>
     * </ul>
     * 300 s (5 min) is a conservative budget covering all of these phases for
     * very large files or slow destination disks.
     */
    private static final int RESULT_TIMEOUT_EXTRA_S = 300;

    /**
     * Computes a file-size-proportional connect timeout for a backup data channel.
     *
     * <p>Mirrors {@code BackupService._data_timeout()} on the desktop so that Android's
     * connect budget always covers the same worst-case scenarios that the PC accounts for.
     *
     * @param fileSizeBytes exact byte count of the file to be transferred
     * @return timeout in whole seconds (minimum {@link #DATA_TIMEOUT_OFFSET_S})
     */
    private static int dataTimeout(long fileSizeBytes) {
        return (int) Math.ceil(DATA_TIMEOUT_MULT * fileSizeBytes) + DATA_TIMEOUT_OFFSET_S;
    }

    /**
     * Computes the connect timeout for waiting on a backup result channel.
     *
     * <p>Equals {@link #dataTimeout(long)} plus {@link #RESULT_TIMEOUT_EXTRA_S} to
     * account for PC-side processing (semaphore wait + classification + file copy)
     * that occurs after Android has finished streaming all the file's bytes.
     *
     * @param fileSizeBytes exact byte count of the file
     * @return timeout in whole seconds
     */
    private static int resultTimeout(long fileSizeBytes) {
        return dataTimeout(fileSizeBytes) + RESULT_TIMEOUT_EXTRA_S;
    }

    private final TransportManager transportManager;
    private final BackupRepository repository;
    private final Context context;
    private final BackupDataSource backupDataSource;

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

    /**
     * All active thread pools for the current session.
     *
     * <p>In the default single-pool path this contains one entry.  When the
     * dual-pool Storage Saver split activates it contains two entries: the media
     * re-encoding pool and the dedicated non-media raw-transfer pool.
     *
     * <p>Kept as an instance field so {@link #stopTransfer()} can call
     * {@code shutdownNow()} on every pool to interrupt threads blocked in result reads.
     * {@link CopyOnWriteArrayList} makes iteration in {@code stopTransfer()} safe
     * against concurrent pool additions during dispatch.
     */
    private final CopyOnWriteArrayList<ExecutorService> activePools =
            new CopyOnWriteArrayList<>();

    public BackupTransferUseCase(TransportManager transportManager,
                                 BackupRepository repository,
                                 Context context,
                                 BackupDataSource backupDataSource) {
        this.transportManager = transportManager;
        this.repository = repository;
        this.context = context.getApplicationContext();
        this.backupDataSource = backupDataSource;
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Executes the full backup transfer for the given file list.
     *
     * <p>Must be called from a background thread (spawned by {@code ConnectivityService}).
     * Each slot thread blocks until the PC sends its per-file result, so progress is
     * driven by actual PC confirmation — not just Android's streaming completion.
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
        activePools.clear();

        final int total = files.size();
        final boolean classify = options != null && options.classifyImages();
        final boolean storageSaver = options != null && options.storageSaver();
        Log.d(TAG, "execute: starting backup transfer — " + total + " files"
                + ", classify=" + classify + ", storageSaver=" + storageSaver);

        try {
            sendManifest(files, classify, storageSaver);

            if (!waitForPcReady()) return;

            final int parallelSlots = Math.min(
                    options != null ? options.parallelSlots() : 1,
                    MAX_PARALLEL_SLOTS);
            Log.d(TAG, "Starting parallel transfer — " + total
                    + " files, " + parallelSlots + " concurrent slot(s)");

            dispatchAllSlots(files, options, parallelSlots, storageSaver);

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
     * Interrupts any slot threads currently blocked in result reads, then signals the PC.
     */
    public void stopTransfer() {
        stopFlag.set(true);
        pauseFlag.set(false); // unblock paused slots so they see stopFlag
        if (aborted.compareAndSet(false, true)) {
            repository.onTransferStopped();
        }
        // Interrupt threads blocked in readFromChannel(resultChannel, timeout) so they
        // exit promptly rather than waiting out the full result timeout.
        for (ExecutorService p : activePools) p.shutdownNow();
        sendControlToPC("stop");
    }

    // ── Protocol orchestration ─────────────────────────────────────────────────

    /**
     * Waits for the PC to send a ready token on {@link BackupChannels#BACKUP_READY_FROM_PC}.
     *
     * <p>Protocol contract: the PC sends {@code "ready"} to accept the session.
     * Any other non-empty token (e.g. {@code "reject"}) means the PC explicitly
     * cancelled — the user dismissed the folder-picker dialog. A null / empty
     * response means the 120-second timeout elapsed (connection drop or PC crash).
     *
     * <p>The two failure modes map to different terminal states:
     * <ul>
     *   <li>{@code null} / empty → {@link BackupRepository#onTransferFailed()} —
     *       network or I/O error; the phone shows an error state.</li>
     *   <li>non-{@code "ready"} token → {@link BackupRepository#onTransferStopped()} —
     *       user-initiated cancel on the PC; the phone shows a "stopped" state,
     *       not an error banner, and can immediately start a new backup.</li>
     * </ul>
     *
     * @return {@code true} if the PC is ready; {@code false} if aborted.
     * @throws Exception if the TauSync read throws unexpectedly.
     */
    private boolean waitForPcReady() throws Exception {
        Log.d(TAG, "Waiting for PC ready (timeout=" + READY_TIMEOUT_SECONDS + "s)");
        String token = transportManager.readFromChannel(
                BackupChannels.BACKUP_READY_FROM_PC.getValue(), READY_TIMEOUT_SECONDS);

        // Timed out or connection dropped — treat as a network / IO failure.
        if (token == null || token.isEmpty()) {
            Log.e(TAG, "PC READY timed out — aborting backup");
            if (aborted.compareAndSet(false, true)) {
                repository.onTransferFailed();
            }
            return false;
        }

        // PC explicitly rejected the session (user cancelled the folder-picker).
        // Use CANCELED_BY_PC — not STOPPED — so BackupFragment stays on-screen
        // and shows a Toast rather than navigating back to ActionsFragment.
        if (!token.trim().equalsIgnoreCase("ready")) {
            Log.d(TAG, "PC rejected backup (response: '" + token.trim() + "') — aborting");
            if (aborted.compareAndSet(false, true)) {
                repository.onTransferCanceledByPc();
            }
            return false;
        }

        Log.d(TAG, "PC ready — beginning slot streams");
        return true;
    }

    /**
     * Dispatches all file-slot tasks, then blocks until every slot finishes.
     *
     * <p><b>Storage Saver ordered split</b> — when {@code storageSaver} is {@code true}
     * <em>and</em> the file list contains both media files (images / videos that will be
     * re-encoded or transcoded) and non-media files (PDFs, APKs, ZIPs, etc.), the method
     * delegates to {@link #dispatchWithDualPool}, which uses a single shared pool but
     * submits non-media tasks before media tasks:
     * <ul>
     *   <li><b>Non-media tasks queued first</b> — threads pick them up immediately on
     *       start, keeping raw-transfer data flowing before any codec work begins.</li>
     *   <li><b>Media tasks queued second</b> — threads that finish a non-media task loop
     *       back to the shared FIFO queue and automatically start on media.  No thread
     *       ever terminates early or sits idle between the two types.</li>
     * </ul>
     *
     * <p><b>Activation condition</b>: if there are <em>no</em> images or videos in the
     * file list the split is skipped entirely (no compression would occur anyway) and
     * all files are handled by a single pool.  The single-pool path is also used when
     * {@code storageSaver} is {@code false} or when the file list is all-media or
     * all-non-media.
     *
     * <p>Both paths share a single {@link CountDownLatch} initialised to the total file
     * count, so {@link #awaitAllSlots} correctly blocks until every slot — media and
     * non-media — has reported its result.
     *
     * @param files         All files to transfer (one slot per file).
     * @param options       User options forwarded to each slot for result handling.
     * @param parallelSlots Max concurrent slot threads (≤ {@link #MAX_PARALLEL_SLOTS}).
     * @param storageSaver  Whether Storage Saver re-encoding is active this session.
     * @throws Exception if {@link #awaitAllSlots} is interrupted.
     */
    private void dispatchAllSlots(List<BackupFileEntry> files,
                                  BackupOptions options,
                                  int parallelSlots,
                                  boolean storageSaver) throws Exception {

        // ── Storage Saver dual-pool split ─────────────────────────────────────
        // Only activate when storageSaver is true AND the list contains BOTH media
        // files (that will be re-encoded/transcoded) and non-media files.
        // "If there is no img/video, don't do it" — skip the split when mediaFiles
        // is empty so we don't waste a thread on a single-type list.
        if (storageSaver) {
            List<BackupFileEntry> mediaFiles = new ArrayList<>();
            List<BackupFileEntry> otherFiles = new ArrayList<>();
            for (BackupFileEntry f : files) {
                String name = new File(f.displayPath()).getName();
                if (isMediaFile(name)) mediaFiles.add(f);
                else otherFiles.add(f);
            }
            if (!mediaFiles.isEmpty() && !otherFiles.isEmpty()) {
                Log.d(TAG, "dispatchAllSlots: Storage Saver ordered split — "
                        + otherFiles.size() + " non-media first, "
                        + mediaFiles.size() + " media after");
                dispatchWithDualPool(mediaFiles, otherFiles, options, parallelSlots);
                return;
            }
            // Fall-through: all-media or all-non-media → single pool below.
        }

        // ── Single pool (default path) ─────────────────────────────────────────
        final int total = files.size();
        CountDownLatch latch = new CountDownLatch(total);
        AtomicInteger confirmed = new AtomicInteger(0);

        ExecutorService singlePool = Executors.newFixedThreadPool(parallelSlots);
        // Register BEFORE submitting so stopTransfer() can find it immediately.
        activePools.add(singlePool);

        for (int i = 0; i < total; i++) {
            final int slotIndex = i;
            final BackupFileEntry entry = files.get(slotIndex);
            // Unique ID for this slot's three TauSync channels (meta / data / result).
            // Using a UUID instead of the sequential index prevents stale REQ frames
            // from a previous cancelled session from being drained by a new session
            // that reuses the same index — the words are globally unique across sessions.
            final String slotId = entry.uuid();
            singlePool.submit(() ->
                    executeSlot(slotId, slotIndex, entry, options,
                            storageSaver, confirmed, total, latch));
        }

        singlePool.shutdown();
        awaitAllSlots(latch);
    }

    /**
     * Polls the latch in 500 ms ticks until all slots have counted down.
     *
     * <p>Breaks early if {@link #aborted} is set or the transport disconnects, then
     * interrupts any remaining slot threads. An {@link InterruptedException} on the
     * polling thread is re-thrown after calling
     * {@link BackupRepository#onTransferFailed()}.
     *
     * @param latch Countdown latch initialised to the total number of files.
     * @throws InterruptedException if the calling thread is interrupted while waiting.
     */
    private void awaitAllSlots(CountDownLatch latch) throws InterruptedException {
        try {
            while (!latch.await(500, TimeUnit.MILLISECONDS)) {
                if (aborted.get() || !transportManager.isConnected()) {
                    Log.w(TAG, "Transfer aborted or disconnected — interrupting remaining slot threads");
                    for (ExecutorService p : activePools) p.shutdownNow();
                    break;
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            Log.e(TAG, "Backup transfer interrupted while waiting for slot results");
            for (ExecutorService p : activePools) p.shutdownNow();
            if (aborted.compareAndSet(false, true)) {
                repository.onTransferFailed();
            }
            throw e;
        }
    }

    // ── Per-slot execution ─────────────────────────────────────────────────────

    /**
     * Executes the full lifecycle of a single backup slot: guard check → stream
     * preparation → meta send → data stream → result read.
     *
     * <p>Extracted from the anonymous {@code Runnable} lambdas in
     * {@link #dispatchAllSlots} and {@link #dispatchWithDualPool} to avoid
     * duplicating the slot body across both pools.
     *
     * @param slotId       UUID identifying this slot's three TauSync channels.
     * @param slotIndex    Zero-based position in the batch (for logging only).
     * @param entry        File to transfer.
     * @param options      User options (delete-after flag, etc.).
     * @param storageSaver {@code true} to attempt image re-encode / video transcode.
     *                     Non-media files always fall through to the raw path in
     *                     {@link #prepareStream} regardless of this flag.
     * @param confirmed    Running total of files confirmed by the PC (shared across slots).
     * @param total        Total files in this session (for progress reporting).
     * @param latch        Countdown latch — counted down in {@code finally} whether
     *                     the slot succeeded or failed.
     */
    private void executeSlot(String slotId,
                             int slotIndex,
                             BackupFileEntry entry,
                             BackupOptions options,
                             boolean storageSaver,
                             AtomicInteger confirmed,
                             int total,
                             CountDownLatch latch) {
        boolean metaSent = false;
        try {
            if (!shouldRun(slotIndex)) return;

            Log.d(TAG, "Slot " + slotIndex + " [" + slotId.substring(0, 8) + "]: "
                    + entry.displayPath() + " (" + entry.sizeBytes() + " B)");

            PreparedStream ps = prepareStream(entry, slotIndex, storageSaver);
            try (InputStream finalStream = ps.stream()) {
                streamMeta(entry, slotId, ps.size());
                metaSent = true;
                streamData(finalStream, slotId, ps.size());
            }
            recordResult(slotId, slotIndex, ps.size(), entry, options, confirmed, total);
        } catch (Exception e) {
            handleSlotError(slotId, slotIndex, metaSent, confirmed, total, e);
        } finally {
            latch.countDown();
        }
    }

    /**
     * Dispatches non-media and media files to a <b>single shared thread pool</b> when
     * Storage Saver is active and the file list contains both types.
     *
     * <p><b>Submission order — non-media first, then media:</b><br>
     * The pool's FIFO task queue means threads pick up non-media tasks immediately
     * on start, keeping raw-transfer data flowing while image / video re-encoding has
     * not yet started.  As each non-media task completes its thread loops back to the
     * shared queue and picks up the next pending task — which will be a media task once
     * the non-media queue drains.  No thread ever terminates early or sits idle:
     * every thread that finishes a non-media file automatically "returns" to help with
     * the remaining photos and videos without any explicit hand-off.
     *
     * <p><b>Why one pool instead of two:</b><br>
     * A separate {@code otherPool} (single thread) would terminate once its non-media
     * tasks are done, wasting one slot of concurrency for the rest of the transfer.
     * A single combined pool avoids this: all {@code parallelSlots} threads stay alive
     * and productive until the very last file is confirmed by the PC.
     *
     * <p>Total concurrent slots = {@code parallelSlots} ≤ {@link #MAX_PARALLEL_SLOTS} = 5,
     * so the PC's {@code MAX_CONCURRENT_RECEIVES} semaphore is never exceeded.
     *
     * <p>The pool is registered in {@link #activePools} before any task is submitted so
     * {@link #stopTransfer()} can interrupt it at any point.
     *
     * <p>Non-media tasks are submitted with {@code storageSaver = false} so
     * {@link #prepareStream} bypasses the {@link BitmapFactory} and
     * {@link VideoTranscoder} codec paths and opens the raw {@link InputStream} directly.
     *
     * @param mediaFiles    Files whose names match {@link #isMediaFile} (images + videos).
     * @param otherFiles    All remaining files (documents, APKs, archives, etc.).
     * @param options       User options forwarded to each slot.
     * @param parallelSlots Number of worker threads in the shared pool.
     * @throws Exception if {@link #awaitAllSlots} is interrupted.
     */
    private void dispatchWithDualPool(List<BackupFileEntry> mediaFiles,
                                      List<BackupFileEntry> otherFiles,
                                      BackupOptions options,
                                      int parallelSlots) throws Exception {
        final int total = mediaFiles.size() + otherFiles.size();
        CountDownLatch latch = new CountDownLatch(total);
        AtomicInteger confirmed = new AtomicInteger(0);

        // One pool for all tasks — threads that finish non-media work automatically
        // pick up media tasks from the shared FIFO queue without any hand-off logic.
        ExecutorService combinedPool = Executors.newFixedThreadPool(parallelSlots);
        // Register BEFORE submitting so stopTransfer() can interrupt immediately.
        activePools.add(combinedPool);

        Log.d(TAG, "dispatchWithDualPool: " + parallelSlots + " thread(s) shared — "
                + otherFiles.size() + " non-media first, then "
                + mediaFiles.size() + " media");

        // ── 1. Non-media files first — raw transfer, no codec work ────────────
        // Queued before media so threads start streaming data immediately.
        // storageSaver=false: prepareStream() skips all re-encode/transcode checks
        // and opens the raw InputStream directly.
        for (int i = 0; i < otherFiles.size(); i++) {
            final int slotIndex = mediaFiles.size() + i;
            final BackupFileEntry entry = otherFiles.get(i);
            final String slotId = entry.uuid();
            combinedPool.submit(() ->
                    executeSlot(slotId, slotIndex, entry, options,
                            false /* storageSaver — raw path */, confirmed, total, latch));
        }

        // ── 2. Media files second — re-encode images / transcode videos ────────
        // Queued after non-media so the initial threads see non-media tasks first.
        // Once all non-media tasks are picked up (fast), every thread that completes
        // one loops back here and picks up the next media task automatically.
        for (int i = 0; i < mediaFiles.size(); i++) {
            final int slotIndex = i;
            final BackupFileEntry entry = mediaFiles.get(slotIndex);
            final String slotId = entry.uuid();
            combinedPool.submit(() ->
                    executeSlot(slotId, slotIndex, entry, options,
                            true /* storageSaver */, confirmed, total, latch));
        }

        combinedPool.shutdown();
        awaitAllSlots(latch);
    }

    /**
     * Checks whether a slot should proceed, handling stop and pause flags.
     *
     * <p>If {@link #stopFlag} is set or the transport is disconnected, sets
     * {@link #aborted} and returns {@code false}. If {@link #pauseFlag} is set,
     * spins in 200 ms increments until either resumed or stopped.
     *
     * @param slotIndex Zero-based slot index (for logging only).
     * @return {@code true} if the slot may continue; {@code false} if it should exit.
     * @throws InterruptedException if the pause-spin sleep is interrupted.
     */
    private boolean shouldRun(int slotIndex) throws InterruptedException {
        if (stopFlag.get() || !transportManager.isConnected()) {
            Log.w(TAG, "Slot " + slotIndex + " skipped — stopped or disconnected");
            aborted.set(true);
            return false;
        }
        while (pauseFlag.get()) {
            if (stopFlag.get()) {
                aborted.set(true);
                return false;
            }
            Thread.sleep(200);
        }
        if (stopFlag.get()) {
            aborted.set(true);
            return false;
        }
        return true;
    }

    /**
     * Resolves the {@link PreparedStream} for a slot — either a re-encoded JPEG
     * (Storage Saver path) or the raw original bytes.
     *
     * <p>When Storage Saver is active and the file is a re-encodable image:
     * <ol>
     *   <li>Decodes the original via {@link BitmapFactory}.</li>
     *   <li>Re-encodes to JPEG at 75 % quality into a {@link ByteArrayOutputStream}
     *       (RAM only — zero disk writes).</li>
     *   <li>Returns a {@link ByteArrayInputStream} wrapping the encoded bytes.</li>
     * </ol>
     * Falls back silently to the raw path on {@link OutOfMemoryError}, a {@code null}
     * bitmap, or any other exception so that a re-encode failure never aborts the slot.
     *
     * @param entry        File whose URI and size are used.
     * @param slotIndex    Zero-based slot index (for logging only).
     * @param storageSaver Whether the Storage Saver option is active.
     * @return A {@link PreparedStream} whose {@code size()} equals the exact byte
     * count that will be written to the data channel.
     * @throws IOException if the raw {@link InputStream} cannot be opened as a fallback.
     */
    private PreparedStream prepareStream(BackupFileEntry entry,
                                         int slotIndex,
                                         boolean storageSaver) throws IOException {
        String fileName = new java.io.File(entry.displayPath()).getName();

        if (storageSaver && isReancodableImage(fileName)) {
            try {
                Uri src = Uri.parse(entry.sourceUri());
                try (InputStream rawIn = context.getContentResolver().openInputStream(src)) {
                    if (rawIn != null) {
                        Bitmap bmp = BitmapFactory.decodeStream(rawIn);
                        if (bmp != null) {
                            ByteArrayOutputStream baos = new ByteArrayOutputStream();
                            bmp.compress(Bitmap.CompressFormat.JPEG, 75, baos);
                            bmp.recycle();
                            byte[] encoded = baos.toByteArray();
                            Log.d(TAG, "Slot " + slotIndex + ": Storage Saver re-encoded "
                                    + entry.sizeBytes() + " B → " + encoded.length + " B");
                            return new PreparedStream(
                                    new ByteArrayInputStream(encoded), encoded.length);
                        } else {
                            Log.w(TAG, "Slot " + slotIndex
                                    + ": BitmapFactory returned null — raw fallback");
                        }
                    }
                }
            } catch (OutOfMemoryError oom) {
                Log.w(TAG, "Slot " + slotIndex + ": OOM re-encoding "
                        + fileName + " — raw fallback");
            } catch (Exception reErr) {
                Log.w(TAG, "Slot " + slotIndex + ": re-encode error ("
                        + reErr.getMessage() + ") — raw fallback");
            }
        }

        // ── Video path: Storage Saver re-encode ──────────────────────────────
        // Mirrors the image path above: transcode to H.264 at a lower bitrate / capped
        // frame-rate via VideoEncoder (MediaCodec + MediaExtractor + MediaMuxer).
        // Falls back silently to the raw path on OOM, null output, or any exception
        // so a transcode failure never aborts the slot.
        if (storageSaver && isTranscodableVideo(fileName)) {
            try {
                Uri src = Uri.parse(entry.sourceUri());
                File transcoded = VideoTranscoder.transcode(
                        context, src, entry.sizeBytes(), slotIndex);
                if (transcoded != null) {
                    long transcodedSize = transcoded.length();
                    Log.d(TAG, "Slot " + slotIndex + ": Storage Saver re-encoded video "
                            + entry.sizeBytes() + " B → " + transcodedSize + " B");
                    // TempFileInputStream deletes the temp file when the stream is closed
                    // (the caller's try-with-resources on PreparedStream.stream()).
                    return new PreparedStream(new TempFileInputStream(transcoded), transcodedSize);
                } else {
                    Log.d(TAG, "Slot " + slotIndex
                            + ": VideoTranscoder skipped (no savings or error) — raw fallback");
                }
            } catch (OutOfMemoryError oom) {
                Log.w(TAG, "Slot " + slotIndex
                        + ": OOM during video transcode — raw fallback");
            } catch (Exception transErr) {
                Log.w(TAG, "Slot " + slotIndex + ": video transcode error ("
                        + transErr.getMessage() + ") — raw fallback");
            }
        }

        // Raw path: open original bytes from ContentResolver.
        InputStream raw = context.getContentResolver()
                .openInputStream(Uri.parse(entry.sourceUri()));
        if (raw == null) {
            throw new IOException("Cannot open InputStream for: " + entry.displayPath());
        }
        return new PreparedStream(raw, entry.sizeBytes());
    }

    /**
     * Reads the PC's per-file result from {@code "backup_file_result_" + slotId},
     * reports it to the repository, and optionally deletes the source file.
     *
     * <p>Uses a size-proportional timeout ({@link #resultTimeout(long)}) that accounts
     * for the PC's semaphore wait, classification time, and disk-copy time.
     *
     * @param slotId     UUID that identifies this slot's three TauSync channels.
     * @param slotIndex  Zero-based position (for logging only).
     * @param streamSize Exact byte count that was streamed (drives the timeout).
     * @param entry      The file — used for source-deletion and logging.
     * @param options    User options — checked for {@code deleteFilesOnBackup}.
     * @param confirmed  Running total of confirmed files (incremented here).
     * @param total      Total number of files in this session (for logging).
     * @throws Exception if the TauSync read fails.
     */
    private void recordResult(String slotId,
                              int slotIndex,
                              long streamSize,
                              BackupFileEntry entry,
                              BackupOptions options,
                              AtomicInteger confirmed,
                              int total) throws Exception {
        String resultChannel = BackupChannels.BACKUP_FILE_RESULT.getValue() + slotId;
        int resultTimeout = resultTimeout(streamSize);
        Log.d(TAG, "Slot " + slotIndex + " streamed — reading PC result"
                + " (timeout=" + resultTimeout + "s)");

        String resultStr = transportManager.readFromChannel(resultChannel, resultTimeout);
        boolean success = BackupFileResult.SUCCESS.getValue()
                .equalsIgnoreCase(resultStr != null ? resultStr.trim() : "");

        int done = confirmed.incrementAndGet();
        repository.onFileTransferred(done, total);
        repository.onFileResult(done, total, success);

        if (success && options != null && options.deleteFilesOnBackup()) {
            backupDataSource.deleteSourceFile(context, entry);
        }
        Log.d(TAG, "Slot " + slotIndex
                + " confirmed by PC (success=" + success
                + ") [" + done + "/" + total + "]");
    }

    /**
     * Handles an exception thrown during slot execution.
     *
     * <p>Two recovery branches:
     * <ul>
     *   <li><b>{@code metaSent == false}</b> — the PC never received metadata and will
     *       never open a result channel. Count the slot down manually as a failure so
     *       the latch is not stuck.</li>
     *   <li><b>{@code metaSent == true}</b> — meta was sent but data or result read
     *       failed. Attempt a short 30-second result read in case the PC detected the
     *       channel error and already emitted a {@code "fail"} token. Count down either
     *       way.</li>
     * </ul>
     *
     * <p>Does <em>not</em> set {@link #aborted} — remaining slots continue regardless
     * of a single slot's failure.
     *
     * @param slotIndex Zero-based slot index.
     * @param metaSent  Whether JSON metadata was successfully written before the error.
     * @param confirmed Running total of confirmed files (incremented here).
     * @param total     Total files in this session.
     * @param e         The exception that caused the slot to fail.
     */
    private void handleSlotError(String slotId,
                                 int slotIndex,
                                 boolean metaSent,
                                 AtomicInteger confirmed,
                                 int total,
                                 Exception e) {
        Log.e(TAG, "Slot " + slotIndex + " failed (metaSent=" + metaSent
                + "): " + e.getMessage(), e);

        if (!metaSent) {
            // PC never received metadata → it will never open a result channel.
            // Count this slot down manually so the UseCase doesn't block forever.
            int done = confirmed.incrementAndGet();
            repository.onFileTransferred(done, total);
            repository.onFileResult(done, total, false);
            Log.d(TAG, "Slot " + slotIndex + " meta-fail: counted down manually ("
                    + done + "/" + total + ")");
        } else {
            // metaSent=true: data stream or result read failed.
            // Try a short-timeout result read — the PC may have detected the
            // data channel error and already sent a "fail" result.
            String resultChannel = BackupChannels.BACKUP_FILE_RESULT.getValue() + slotId;
            try {
                String resultStr = transportManager.readFromChannel(resultChannel, 30);
                boolean success = BackupFileResult.SUCCESS.getValue()
                        .equalsIgnoreCase(resultStr != null ? resultStr.trim() : "");
                int done = confirmed.incrementAndGet();
                repository.onFileTransferred(done, total);
                repository.onFileResult(done, total, success);
                Log.d(TAG, "Slot " + slotIndex
                        + " late-result after data error: success=" + success
                        + " [" + done + "/" + total + "]");
            } catch (Exception re) {
                // PC didn't send a result — count as failure.
                int done = confirmed.incrementAndGet();
                repository.onFileTransferred(done, total);
                repository.onFileResult(done, total, false);
                Log.d(TAG, "Slot " + slotIndex
                        + " no PC result after data error — counted as failure ("
                        + done + "/" + total + ")");
            }
        }
        // Do NOT set aborted — remaining slots continue regardless.
    }

    // ── Channel I/O ───────────────────────────────────────────────────────────

    /**
     * Sends the lightweight manifest on
     * {@link BackupChannels#BACKUP_MANIFEST_FROM_ANDROID}.
     *
     * <p>Wire format:
     * {@code {"file_count": N, "files_bytes": S, "classify": true|false, "storage_saver": true|false}}.
     *
     * <p>{@code files_bytes} is always the sum of <em>original</em> file sizes — a safe
     * upper bound for disk-space checks on the PC side. When {@code storage_saver} is
     * {@code true}, actual bytes transferred will be lower (re-encoded images are smaller).
     * The PC uses the flag to display "Up to X GB · Storage Saver on" instead of a hard
     * byte count in its folder-picker dialog.
     *
     * @param files        The file list whose count and combined original size are written.
     * @param classify     {@code true} to ask the PC to run content classification.
     * @param storageSaver {@code true} when the Storage Saver option is active.
     * @throws Exception if the TauSync write fails.
     */
    private void sendManifest(List<BackupFileEntry> files,
                              boolean classify,
                              boolean storageSaver) throws Exception {
        long totalSizeBytes = 0;
        for (BackupFileEntry entry : files) {
            totalSizeBytes += entry.sizeBytes();
        }

        JSONObject manifest = new JSONObject();
        manifest.put("file_count", files.size());
        manifest.put("files_bytes", totalSizeBytes);
        manifest.put("classify", classify);
        manifest.put("storage_saver", storageSaver);

        Log.d(TAG, "Sending manifest: " + manifest);
        transportManager.writeToChannel(
                BackupChannels.BACKUP_MANIFEST_FROM_ANDROID.getValue(),
                manifest.toString());
    }

    /**
     * Sends the per-file JSON metadata on {@code "backup_slot_meta_" + slotIndex}.
     *
     * <p>Wire format: {@code {"name": "photo.jpg", "size": N, "mtime": T, "rel_path": "…"}}.
     * The PC uses {@code size} to open the data channel with a proportional timeout and
     * {@code rel_path} (folder-mode only) to reconstruct the directory tree.
     *
     * <p>{@code streamSize} is the <em>actual</em> byte count that will flow through the
     * data channel — equal to the original file size for raw transfers, or the re-encoded
     * size when Storage Saver re-encoded the file. The PC reads exactly {@code streamSize}
     * bytes from the data channel; any mismatch corrupts the transfer.
     *
     * @param entry      File whose name, mtime, and rel_path are written.
     * @param slotId     UUID that identifies this slot's three TauSync channels.
     * @param streamSize Exact byte count that will be streamed on the data channel.
     * @throws Exception if the TauSync channel write fails (propagates — NOT swallowed).
     */
    private void streamMeta(BackupFileEntry entry, String slotId, long streamSize) throws Exception {
        String metaChannel = BackupChannels.BACKUP_FILE_META_SLOT.getValue() + slotId;
        String fileName = new java.io.File(entry.displayPath()).getName();

        Log.d(TAG, "streamMeta [" + slotId.substring(0, 8) + "]: " + entry.displayPath()
                + " streamSize=" + streamSize + " B");

        JSONObject meta = new JSONObject();
        meta.put("name", fileName);
        meta.put("size", streamSize);          // actual bytes to expect on data channel
        meta.put("mtime", entry.mtimeMs());
        // When Storage Saver re-encoded this file, include the original size so the PC
        // can progressively subtract the savings from its running _total_bytes denominator,
        // keeping the overall progress bar accurate. Omitted when sizes are equal (raw
        // fallback or non-media file) so the PC applies zero correction — no-op.
        if (streamSize != entry.sizeBytes()) {
            meta.put("orig_size", entry.sizeBytes());
        }
        // Include rel_path only when available (MODE_FOLDER); absent in MODE_ALL_MEDIA.
        String relPath = entry.relPath();
        if (relPath != null && !relPath.isEmpty()) {
            meta.put("rel_path", relPath);
        }

        transportManager.writeToChannel(metaChannel, meta.toString());
    }

    /**
     * Streams bytes from a pre-prepared {@link InputStream} on
     * {@code "backup_slot_data_" + slotIndex}.
     *
     * <p>The stream must already be open and will be read to exhaustion. The caller
     * is responsible for closing it (typically via try-with-resources in the calling
     * scope). The stream may carry either the original file bytes or a re-encoded JPEG
     * produced by Storage Saver mode — the PC receives them identically.
     *
     * <p>Connect timeout is proportional to {@code streamSize} (mirrors
     * {@code backup.py._data_timeout}): {@code ceil(1/5_000_000 × bytes) + 30 s}.
     *
     * @param stream     Pre-opened stream positioned at the start of the data.
     * @param slotId     UUID that identifies this slot's three TauSync channels.
     * @param streamSize Exact byte count expected in the stream (drives timeout).
     * @throws Exception if the channel write fails.
     */
    private void streamData(InputStream stream, String slotId, long streamSize) throws Exception {
        String dataChannel = BackupChannels.BACKUP_FILE_DATA_SLOT.getValue() + slotId;
        int dataTimeoutSec = dataTimeout(streamSize);

        Log.d(TAG, "streamData [" + slotId.substring(0, 8) + "]: timeout=" + dataTimeoutSec + "s"
                + " streamSize=" + streamSize + " B");

        transportManager.streamInputStreamToChannel(dataChannel, stream, dataTimeoutSec);
    }


    /**
     * Holds the resolved {@link InputStream} and exact byte count for a slot,
     * produced by {@link #prepareStream(BackupFileEntry, int, boolean)}.
     *
     * <p>Three possible stream implementations:
     * <ol>
     *   <li>{@link ByteArrayInputStream} — re-encoded JPEG from the Storage Saver image path.</li>
     *   <li>{@link TempFileInputStream} — transcoded MP4 from the Storage Saver video path;
     *       auto-deletes its temp file in {@code getCacheDir()} on {@code close()}.</li>
     *   <li>Raw {@link InputStream} from
     *       {@link android.content.ContentResolver#openInputStream(Uri)} — original bytes.</li>
     * </ol>
     * In all cases {@link #size()} equals the exact number of bytes that will be written
     * to the TauSync data channel, matching the value declared in {@code meta["size"]}.
     */
    private record PreparedStream(InputStream stream, long size) {
    }

    /**
     * Returns {@code true} if {@code fileName} is either a re-encodable image or a
     * transcodable video — i.e. a file type that Storage Saver will compress.
     *
     * <p>Used by {@link #dispatchAllSlots} to partition the file list into media and
     * non-media buckets before activating the dual-pool split.  Combining both checks
     * here prevents duplicating the extension-union logic at the call site.
     *
     * @param fileName Bare filename including extension.
     * @return {@code true} if the file should be routed to the media pool.
     */
    private static boolean isMediaFile(String fileName) {
        return isReancodableImage(fileName) || isTranscodableVideo(fileName);
    }

    /**
     * Returns {@code true} for image extensions that can be losslessly round-tripped
     * through {@link BitmapFactory} + {@link Bitmap#compress} for Storage Saver
     * quality reduction.
     *
     * <p>GIF is excluded (re-encoding destroys animation). RAW formats (DNG, CR2, ARW)
     * are excluded — a 75 % JPEG re-encode of a RAW file is meaningless. Videos are
     * handled separately via {@link #isTranscodableVideo}.
     *
     * @param fileName Bare filename including extension.
     * @return {@code true} if this file should be re-encoded under Storage Saver.
     */
    private static boolean isReancodableImage(String fileName) {
        if (fileName == null || fileName.isEmpty()) return false;
        String lower = fileName.toLowerCase(Locale.ROOT);
        return lower.endsWith(".jpg")
                || lower.endsWith(".jpeg")
                || lower.endsWith(".heic")
                || lower.endsWith(".heif")
                || lower.endsWith(".png")
                || lower.endsWith(".webp")
                || lower.endsWith(".bmp");
    }

    /**
     * Returns {@code true} for video extensions whose container and codec are supported
     * by {@link VideoTranscoder} (platform {@link android.media.MediaCodec} pipeline).
     *
     * <p>All listed formats are decodable by Android's built-in software / hardware
     * decoders on API 29+. The output is always MP4 / H.264 regardless of input codec.
     *
     * @param fileName Bare filename including extension.
     * @return {@code true} if this file should be transcoded under Storage Saver.
     */
    private static boolean isTranscodableVideo(String fileName) {
        if (fileName == null || fileName.isEmpty()) return false;
        String lower = fileName.toLowerCase(Locale.ROOT);
        return lower.endsWith(".mp4")
                || lower.endsWith(".3gp")
                || lower.endsWith(".mov")
                || lower.endsWith(".m4v")
                || lower.endsWith(".mkv")
                || lower.endsWith(".webm")
                || lower.endsWith(".ts");
    }

    /**
     * Wraps a {@link FileInputStream} on a temp file produced by {@link VideoTranscoder}
     * and <em>deletes</em> the underlying file when {@link #close()} is called.
     *
     * <p>The caller's try-with-resources on {@link PreparedStream#stream()} always
     * invokes {@link #close()}, so the temp file in {@code getCacheDir()} is removed
     * whether the slot succeeds, errors, or is interrupted — no cache leak.
     */
    private static final class TempFileInputStream extends FileInputStream {

        private final File tempFile;

        TempFileInputStream(File file) throws FileNotFoundException {
            super(file);
            this.tempFile = file;
        }

        @Override
        public void close() throws IOException {
            try {
                super.close();
            } finally {
                if (!tempFile.delete()) {
                    Log.w(TAG, "TempFileInputStream: failed to delete " + tempFile.getName());
                }
            }
        }
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

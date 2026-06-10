package com.example.android.network.handlers;

import android.content.Context;
import android.util.Log;

import com.example.android.data.datasource.BackupDataSource;
import com.example.android.domain.entities.BackupFileEntry;
import com.example.android.domain.entities.BackupOptions;
import com.example.android.enums.BackupChannels;
import com.example.android.enums.BackupFileResult;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.BackupRepository;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Handles per-file transfer results sent by the PC on
 * {@code backup_file_result_{slotIndex}} channels during an active backup session.
 *
 * <h3>Registration</h3>
 * <p>Registered under the prefix key
 * {@link BackupChannels#BACKUP_FILE_RESULT} ({@code "backup_file_result_"}).
 * {@link ChannelHandlerRegistry}'s prefix-match fallback routes
 * {@code "backup_file_result_0"}, {@code "backup_file_result_1"}, etc. here — one
 * registration covers the entire batch regardless of file count.
 *
 * <h3>Lifecycle</h3>
 * <p>Created and registered at the start of
 * {@link com.example.android.domain.usecases.BackupTransferUseCase#execute} and
 * unregistered by the UseCase once all results have been counted down (or on abort).
 * The UseCase retains ownership of the latch and the abort flag; this handler only
 * reads from the PC and counts down.
 *
 * <h3>Protocol</h3>
 * <p>The PC calls {@code connect("backup_file_result_N")} once per file after it
 * finishes receiving, screening, and saving it. The polling loop detects the channel
 * via {@code getPeerWaitingWords()}, the registry dispatches here, and
 * {@link #onPeerRequest(String)} reads the one-word payload:
 * {@link BackupFileResult#SUCCESS} ({@code "succ"}) or
 * {@link BackupFileResult#FAILURE} ({@code "fail"}).
 *
 * <h3>Threading</h3>
 * <p>Called on {@code PeerRequestHandlerThread}. The {@code readFromChannel} call is
 * fast because the PC has already opened the channel before the polling loop sees it
 * — no additional blocking handshake is needed.
 */
public class BackupReceivedChannelHandler implements ChannelHandler {

    private static final String TAG = "BackupReceivedHandler";

    /** Prefix of all per-file result channels; suffix is the slot index. */
    private static final String CHANNEL_PREFIX = BackupChannels.BACKUP_FILE_RESULT.getValue();

    private final TransportManager transportManager;
    private final BackupRepository repository;
    private final BackupDataSource backupDataSource;
    private final Context context;
    private final BackupOptions options;
    private final List<BackupFileEntry> files;
    private final int total;

    /**
     * Running count of files confirmed by the PC so far.
     * Shared with the UseCase so it can be inspected for logging.
     */
    private final AtomicInteger confirmedCount;

    /**
     * Shared abort flag — set by UseCase on stop/failure.
     * Checked before updating repository state so stale results don't
     * corrupt a subsequent backup session.
     */
    private final AtomicBoolean aborted;

    /**
     * Counts down once per confirmed result.
     * When it reaches zero the UseCase's poll loop unblocks and calls
     * {@link BackupRepository#onTransferComplete()}.
     */
    private final CountDownLatch resultsLatch;

    public BackupReceivedChannelHandler(
            TransportManager transportManager,
            BackupRepository repository,
            BackupDataSource backupDataSource,
            Context context,
            BackupOptions options,
            List<BackupFileEntry> files,
            int total,
            AtomicInteger confirmedCount,
            AtomicBoolean aborted,
            CountDownLatch resultsLatch) {
        this.transportManager = transportManager;
        this.repository = repository;
        this.backupDataSource = backupDataSource;
        this.context = context.getApplicationContext();
        this.options = options;
        this.files = files;
        this.total = total;
        this.confirmedCount = confirmedCount;
        this.aborted = aborted;
        this.resultsLatch = resultsLatch;
    }

    // ── ChannelHandler ────────────────────────────────────────────────────────

    /**
     * Returns the prefix key under which this handler is registered.
     * The registry's prefix-match fallback ensures it receives all channels
     * whose name starts with this value.
     */
    @Override
    public String getChannelName() {
        return CHANNEL_PREFIX;
    }

    /**
     * Not used — the registry always dispatches via {@link #onPeerRequest(String)}.
     */
    @Override
    public void onPeerRequest() {
        Log.w(TAG, "onPeerRequest() called without channel name — ignored");
    }

    /**
     * Called by the registry when the PC opens a {@code backup_file_result_{N}} channel.
     *
     * <ol>
     *   <li>Parses the slot index from the channel suffix.</li>
     *   <li>Reads the result token ({@code "succ"} or {@code "fail"}) from the channel.</li>
     *   <li>Updates {@link BackupRepository#onFileTransferred} (progress counter) and
     *       {@link BackupRepository#onFileResult} (failed-count tally).</li>
     *   <li>If the result is {@code "succ"} and delete-after-backup is enabled, deletes
     *       the source file and any now-empty ancestor directories.</li>
     *   <li>Counts down the shared {@link #resultsLatch} to signal the UseCase.</li>
     * </ol>
     *
     * @param channel The exact channel name, e.g. {@code "backup_file_result_3"}.
     */
    @Override
    public void onPeerRequest(String channel) {
        // ── Parse slot index ──────────────────────────────────────────────────
        int slotIndex;
        try {
            slotIndex = Integer.parseInt(channel.substring(CHANNEL_PREFIX.length()));
        } catch (NumberFormatException e) {
            Log.e(TAG, "Cannot parse slot index from channel: " + channel);
            resultsLatch.countDown();   // prevent UseCase from blocking forever
            return;
        }

        // ── Read PC result ────────────────────────────────────────────────────
        String result;
        try {
            result = transportManager.readFromChannel(channel);
        } catch (Exception e) {
            Log.e(TAG, "Slot " + slotIndex + ": failed to read result from PC: " + e.getMessage(), e);
            // Treat read failure as a transfer failure for this slot but keep the
            // batch running — count it as "fail" so the failed-count tally is correct.
            result = BackupFileResult.FAILURE.getValue();
        }

        boolean ok = BackupFileResult.SUCCESS.getValue().equals(result);
        Log.d(TAG, "Slot " + slotIndex + " PC result: " + result);

        // ── Update repository (same calls as before — just moved here) ────────
        int done = confirmedCount.incrementAndGet();
        repository.onFileTransferred(done, total);
        repository.onFileResult(done, total, ok);
        Log.d(TAG, "Slot " + slotIndex + " confirmed by PC — " + done + "/" + total
                + " (" + (ok ? "succ" : "fail") + ")");

        // ── Delete-after-backup (best-effort, only on explicit PC success) ────
        // A "fail" result, a read error, or aborted state must never delete the source.
        if (ok && !aborted.get()
                && options != null && options.isDeleteFilesOnBackup()
                && slotIndex < files.size()) {
            BackupFileEntry entry = files.get(slotIndex);
            boolean deleted = backupDataSource.deleteSourceFile(context, entry);
            Log.d(TAG, "Slot " + slotIndex + ": deleteFilesOnBackup — "
                    + (deleted ? "deleted " : "failed to delete ")
                    + entry.getDisplayPath());
            if (deleted) {
                backupDataSource.deleteEmptyParentFolders(entry);
            }
        }

        // ── Signal UseCase ────────────────────────────────────────────────────
        resultsLatch.countDown();
    }

    @Override
    public void onShutdown() {
        // Called when ConnectivityService.cleanup() → handlerRegistry.shutdownAll().
        // The UseCase's poll loop exits via isConnected() == false in this scenario,
        // so we do not touch the latch here — the UseCase is responsible for cleanup.
        Log.d(TAG, "BackupReceivedChannelHandler shut down — "
                + confirmedCount.get() + "/" + total + " confirmed");
    }
}

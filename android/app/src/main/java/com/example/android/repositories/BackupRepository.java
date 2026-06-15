package com.example.android.repositories;

import android.net.Uri;
import android.util.Log;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.domain.entities.BackupFileEntry;
import com.example.android.domain.entities.BackupOptions;
import com.example.android.domain.enums.BackupScanStatus;
import com.example.android.domain.enums.BackupTransferStatus;
import com.example.android.viewmodel.BackupViewModel;

import java.util.Collections;
import java.util.List;

/**
 * Repository for the backup scan phase (Android → PC file enumeration).
 *
 * <p>Singleton — mirrors the {@code SendFileRepository} / {@code ReceiveFileRepository}
 * pattern used throughout this codebase.
 *
 * <p>Lifecycle of a scan:
 * <pre>
 *   IDLE → SCANNING → READY
 *                   ↘ FAILED
 *   (terminal state) → IDLE via reset()
 * </pre>
 *
 * <p>{@link BackupViewModel} calls {@link #requestScan} to start a scan.
 * The ViewModel then spawns a background thread, runs
 * {@link com.example.android.domain.usecases.ScanBackupFilesUseCase}, and
 * feeds the result back via {@link #onScanComplete} / {@link #onScanFailed}.
 *
 * <p>No {@code ConnectivityService} involvement — the scan is entirely local.
 */
public class BackupRepository {

    private static final String TAG = "BackupRepository";

    private static BackupRepository instance;

    // ── Scan LiveData ─────────────────────────────────────────────────────────

    private final MutableLiveData<BackupScanStatus> scanStatus =
            new MutableLiveData<>(BackupScanStatus.IDLE);

    private final MutableLiveData<List<BackupFileEntry>> scannedFiles =
            new MutableLiveData<>(Collections.emptyList());

    // ── Transfer LiveData ─────────────────────────────────────────────────────

    /** Current lifecycle state of the backup transfer phase. */
    private final MutableLiveData<BackupTransferStatus> transferStatus =
            new MutableLiveData<>(BackupTransferStatus.IDLE);

    /** Number of files successfully sent so far in the current batch. */
    private final MutableLiveData<Integer> transferSent =
            new MutableLiveData<>(0);

    /** Total number of files in the current backup batch. */
    private final MutableLiveData<Integer> transferTotal =
            new MutableLiveData<>(0);

    /** Number of files the PC reported as transfer failures ({@code "fail"}) so far. */
    private final MutableLiveData<Integer> failedCount =
            new MutableLiveData<>(0);

    // ── Action listeners ──────────────────────────────────────────────────────

    /**
     * Implemented by {@link com.example.android.viewmodel.BackupViewModel}.
     * Bridges the UI scan request to the background-thread UseCase execution.
     */
    public interface ScanActionListener {
        /**
         * User tapped Start Backup — begin scanning on a background thread.
         *
         * @param mode      {@code "all_media"} or {@code "folder"}
         * @param folderUri SAF tree URI; non-null only when {@code mode == "folder"}
         */
        void onScanRequested(String mode, Uri folderUri);
    }

    /**
     * Implemented by {@code ConnectivityService}.
     * Bridges the scan-complete transfer request to the background-thread UseCase execution.
     */
    public interface TransferActionListener {
        /**
         * Scan finished — begin sending files to the PC on a background thread.
         *
         * @param files   Non-empty list of files to transfer.
         * @param options User-configured backup options (e.g. {@code classify_images}).
         */
        void onTransferRequested(List<BackupFileEntry> files, BackupOptions options);
    }

    /**
     * Implemented by {@code ConnectivityService} (where {@code BackupTransferUseCase}
     * is accessible).  Routes pause / resume / stop requests from the ViewModel or
     * Fragment to the running UseCase on its background thread.
     */
    public interface ControlActionListener {
        void onPauseRequested();
        void onResumeRequested();
        void onStopRequested();
    }

    private ScanActionListener actionListener;
    private TransferActionListener transferActionListener;
    private ControlActionListener controlActionListener;

    /**
     * Options captured when {@link #requestScan} is called, consumed by
     * {@link #onScanComplete} to auto-trigger {@link #requestTransfer}. Since the
     * Fragment that started the scan may already be gone (immediate return-to-main
     * UX), the repository — not the UI — owns this handoff.
     */
    private BackupOptions pendingOptions = new BackupOptions(true);

    /**
     * Guard flag that prevents a stale scan from auto-triggering a transfer on a
     * new connection session.
     *
     * <p>Set to {@code true} in {@link #requestScan} (user explicitly started a
     * backup).  Cleared to {@code false} in {@link #reset} (called by
     * {@code ConnectivityService.cleanup()} on disconnect).
     *
     * <p>If the connection drops while a scan is in-flight, the scan thread keeps
     * running (pure local I/O). When it eventually calls {@link #onScanComplete},
     * this flag is already {@code false} — the result is discarded instead of
     * being forwarded to a brand-new connection session's
     * {@link TransferActionListener}.
     */
    private volatile boolean scanActiveForTransfer = false;

    // ── Singleton ─────────────────────────────────────────────────────────────

    private BackupRepository() {
    }

    public static synchronized BackupRepository getInstance() {
        if (instance == null) {
            instance = new BackupRepository();
        }
        return instance;
    }

    // ── Listener registration ─────────────────────────────────────────────────

    /**
     * Registered by {@link com.example.android.viewmodel.BackupViewModel} once it
     * is ready to handle scan requests.
     */
    public void setActionListener(ScanActionListener listener) {
        this.actionListener = listener;
    }

    /**
     * Registered by {@code ConnectivityService} so it can receive the transfer request
     * and execute it on a background thread — keeping the repository transport-free.
     */
    public void setTransferActionListener(TransferActionListener listener) {
        this.transferActionListener = listener;
    }

    /**
     * Registered by {@code ConnectivityService} (where {@code BackupTransferUseCase}
     * is accessible) so pause / resume / stop requests from the UI can reach the
     * running UseCase.
     */
    public void setControlActionListener(ControlActionListener listener) {
        this.controlActionListener = listener;
    }

    // ── Observers (for ViewModel / Fragment / ConnectivityService) ────────────

    /**
     * Returns {@code true} when a scan or transfer is currently running or paused.
     *
     * <p>Safe to call from any thread — reads the last-posted LiveData values
     * synchronously, so there is a negligible window at the very start of
     * {@link #requestScan} (before {@code postValue} delivers SCANNING to the
     * main thread) where this may still return {@code false}.  In practice the
     * UI check in {@code ActionsFragment} is always on the main thread and well
     * after the previous scan was dispatched, so this window is never hit.
     *
     * @return {@code true} if a scan is running or a transfer is SENDING / PAUSED.
     */
    public boolean isBackupActive() {
        BackupScanStatus scan = scanStatus.getValue();
        BackupTransferStatus xfer = transferStatus.getValue();
        boolean scanning = scan == BackupScanStatus.SCANNING;
        boolean transferring = xfer == BackupTransferStatus.SENDING
                || xfer == BackupTransferStatus.PAUSED;
        return scanning || transferring;
    }

    /**
     * @return LiveData tracking the current scan lifecycle state.
     */
    public LiveData<BackupScanStatus> getScanStatus() {
        return scanStatus;
    }

    /**
     * @return LiveData containing the most recently scanned file list.
     * Only meaningful when {@link #getScanStatus()} is {@code READY}.
     */
    public LiveData<List<BackupFileEntry>> getScannedFiles() {
        return scannedFiles;
    }

    /**
     * @return LiveData tracking the backup transfer lifecycle state.
     *         Observed by {@code ConnectivityService} to drive the progress notification.
     */
    public LiveData<BackupTransferStatus> getTransferStatus() {
        return transferStatus;
    }

    /**
     * @return LiveData with the count of files successfully sent so far.
     */
    public LiveData<Integer> getTransferSent() {
        return transferSent;
    }

    /**
     * @return LiveData with the total number of files in the current batch.
     */
    public LiveData<Integer> getTransferTotal() {
        return transferTotal;
    }

    /**
     * @return LiveData with the count of files the PC reported as transfer
     * failures ({@code "fail"}) so far in the current batch.
     */
    public LiveData<Integer> getFailedCount() {
        return failedCount;
    }

    // ── UI → Repository (called by Fragment / BackupViewModel) ───────────────

    /**
     * Initiates a scan — transitions IDLE → SCANNING and fires the action listener.
     *
     * @param mode      Backup mode constant from {@link com.example.android.domain.usecases.ScanBackupFilesUseCase}.
     * @param folderUri SAF tree URI; must be non-null when {@code mode == "folder"}.
     * @param options   User-configured backup options — stashed for {@link #onScanComplete}
     *                  to forward to {@link #requestTransfer} once the scan finishes.
     */
    public void requestScan(String mode, Uri folderUri, BackupOptions options) {
        if (isBackupActive()) {
            Log.w(TAG, "requestScan: backup already active — ignoring duplicate request");
            return;
        }
        Log.d(TAG, "requestScan: mode=" + mode + " options=" + options);
        this.pendingOptions = (options != null) ? options : new BackupOptions(true);
        this.scanActiveForTransfer = true;   // arm: user explicitly started this scan
        scanStatus.postValue(BackupScanStatus.SCANNING);

        if (actionListener != null) {
            actionListener.onScanRequested(mode, folderUri);
        } else {
            Log.w(TAG, "No ScanActionListener registered — cannot start scan");
            scanStatus.postValue(BackupScanStatus.FAILED);
        }
    }

    // ── State transitions (called by BackupViewModel after UseCase finishes) ──

    /**
     * Called by {@link com.example.android.viewmodel.BackupViewModel} when the scan
     * succeeded.
     *
     * <p>The Fragment that initiated the scan has already returned to the main
     * screen (immediate return-to-main UX), so this method — not the UI — drives
     * the handoff to the transfer phase: a non-empty result immediately calls
     * {@link #requestTransfer} using the {@link #pendingOptions} captured in
     * {@link #requestScan}. {@code scanStatus} returns straight to {@code IDLE}
     * since no UI observes the {@code READY} state anymore.
     */
    public void onScanComplete(List<BackupFileEntry> files) {
        Log.d(TAG, "onScanComplete: " + files.size() + " files");
        scannedFiles.postValue(files);
        scanStatus.postValue(BackupScanStatus.IDLE);

        // Guard: if reset() was called while the scan was in-flight (e.g. the
        // connection dropped mid-scan), do NOT forward to requestTransfer().
        // The scan result belongs to a connection session that no longer exists.
        if (!scanActiveForTransfer) {
            Log.w(TAG, "onScanComplete: scan was invalidated (connection dropped) — discarding result");
            return;
        }
        scanActiveForTransfer = false; // consume: one scan → one transfer

        if (files.isEmpty()) {
            Log.w(TAG, "onScanComplete: no files found — nothing to back up");
            scanStatus.postValue(BackupScanStatus.EMPTY);
            return;
        }

        requestTransfer(files, pendingOptions);
    }

    /**
     * Called by {@link com.example.android.viewmodel.BackupViewModel} when the scan
     * threw an exception.  SCANNING → FAILED.
     */
    public void onScanFailed() {
        Log.e(TAG, "onScanFailed");
        scannedFiles.postValue(Collections.emptyList());
        scanStatus.postValue(BackupScanStatus.FAILED);
    }

    /**
     * Resets to IDLE after the UI has acknowledged a terminal state
     * (READY / FAILED), or when the connection is dropped by
     * {@code ConnectivityService.cleanup()}.
     *
     * <p>Clears {@link #scanActiveForTransfer} so any scan that is still running
     * in the background (pure local I/O, unaffected by network) will discard its
     * result in {@link #onScanComplete} rather than auto-triggering a transfer on
     * the next connection session.
     */
    public void reset() {
        scanActiveForTransfer = false;   // invalidate any in-flight scan
        scannedFiles.postValue(Collections.emptyList());
        scanStatus.postValue(BackupScanStatus.IDLE);
    }

    // ── Transfer: UI → Repository (called by BackupViewModel) ────────────────

    /**
     * Initiates a backup transfer — transitions IDLE → SENDING and fires the
     * transfer action listener so {@code ConnectivityService} can start the
     * background UseCase.
     *
     * @param files   Non-empty scanned file list ready to send.
     * @param options User-configured backup options (e.g. {@code classify_images}).
     */
    public void requestTransfer(List<BackupFileEntry> files, BackupOptions options) {
        if (files == null || files.isEmpty()) {
            Log.w(TAG, "requestTransfer called with empty list — ignoring");
            return;
        }
        Log.d(TAG, "requestTransfer: " + files.size() + " files, options=" + options);
        transferSent.postValue(0);
        transferTotal.postValue(files.size());
        transferStatus.postValue(BackupTransferStatus.SENDING);

        if (transferActionListener != null) {
            transferActionListener.onTransferRequested(files, options);
        } else {
            Log.w(TAG, "No TransferActionListener — is ConnectivityService running?");
            transferStatus.postValue(BackupTransferStatus.FAILED);
        }
    }

    // ── Transfer: State transitions (called by BackupTransferUseCase) ─────────

    /**
     * Called by {@code BackupTransferUseCase} after each file is successfully sent.
     * Updates the progress counter; keeps status as SENDING.
     *
     * @param sent  Running total of files sent so far.
     * @param total Total files in this batch.
     */
    public void onFileTransferred(int sent, int total) {
        Log.d(TAG, "onFileTransferred: " + sent + "/" + total);
        transferSent.postValue(sent);
        transferTotal.postValue(total);
        // Status stays SENDING — final state set by onTransferComplete / onTransferFailed.
    }

    /**
     * Called by {@code BackupTransferUseCase} when the PC sends a per-file transfer
     * result on the {@code backup_file_result_{i}} channel.
     *
     * <p>A result of {@code success=false} means a transport/IO problem occurred while
     * the PC was receiving or saving the file — distinct from PC-local content-screening
     * rejections (corrupt/duplicate/filtered), which are still reported as
     * {@code success=true} since the transfer itself completed.
     *
     * @param index   1-based index of the reported file.
     * @param total   Total files in this backup batch.
     * @param success {@code true} when the PC reported
     *                {@link com.example.android.enums.BackupFileResult#SUCCESS};
     *                {@code false} when it reported
     *                {@link com.example.android.enums.BackupFileResult#FAILURE}.
     */
    public void onFileResult(int index, int total, boolean success) {
        Log.d(TAG, "onFileResult: " + index + "/" + total
                + " — " + (success ? "succ" : "fail"));
        if (!success) {
            Integer current = failedCount.getValue();
            failedCount.postValue((current == null ? 0 : current) + 1);
        }
    }

    /**
     * Called by {@code BackupTransferUseCase} when all files have been processed.
     * SENDING → COMPLETED.
     */
    public void onTransferComplete() {
        Log.d(TAG, "onTransferComplete");
        transferStatus.postValue(BackupTransferStatus.COMPLETED);
    }

    /**
     * Called by {@code BackupTransferUseCase} on network error or I/O failure.
     * (any state) → FAILED.
     */
    public void onTransferFailed() {
        Log.e(TAG, "onTransferFailed");
        transferStatus.postValue(BackupTransferStatus.FAILED);
    }

    /**
     * Called by {@code BackupTransferUseCase} when the user pauses the transfer.
     * SENDING → PAUSED.
     */
    public void onTransferPaused() {
        Log.d(TAG, "onTransferPaused");
        transferStatus.postValue(BackupTransferStatus.PAUSED);
    }

    /**
     * Called by {@code BackupTransferUseCase} when the user resumes after a pause.
     * PAUSED → SENDING.
     */
    public void onTransferResumed() {
        Log.d(TAG, "onTransferResumed");
        transferStatus.postValue(BackupTransferStatus.SENDING);
    }

    /**
     * Called by {@code BackupTransferUseCase} when the user intentionally stops the
     * transfer via the phone notification.  (any state) → STOPPED.
     */
    public void onTransferStopped() {
        Log.d(TAG, "onTransferStopped");
        transferStatus.postValue(BackupTransferStatus.STOPPED);
    }

    /**
     * Called by {@code BackupTransferUseCase} when the PC explicitly rejects the
     * session before any file is sent — the PC user dismissed the folder-picker dialog
     * ({@code waitForPcReady()} received a non-{@code "ready"} token).
     * (any state) → CANCELED_BY_PC.
     *
     * <p>Distinct from {@link #onTransferStopped()} so that {@code BackupFragment} can
     * remain on-screen and show a Toast instead of navigating back.
     */
    public void onTransferCanceledByPc() {
        Log.d(TAG, "onTransferCanceledByPc");
        transferStatus.postValue(BackupTransferStatus.CANCELED_BY_PC);
    }

    // ── Control: UI → Repository (pause / resume / stop) ─────────────────────

    /** Routes a pause request to the registered {@link ControlActionListener}. */
    public void requestPause() {
        if (controlActionListener != null) {
            controlActionListener.onPauseRequested();
        } else {
            Log.w(TAG, "requestPause: no ControlActionListener registered");
        }
    }

    /** Routes a resume request to the registered {@link ControlActionListener}. */
    public void requestResume() {
        if (controlActionListener != null) {
            controlActionListener.onResumeRequested();
        } else {
            Log.w(TAG, "requestResume: no ControlActionListener registered");
        }
    }

    /** Routes a stop request to the registered {@link ControlActionListener}. */
    public void requestStop() {
        if (controlActionListener != null) {
            controlActionListener.onStopRequested();
        } else {
            Log.w(TAG, "requestStop: no ControlActionListener registered");
        }
    }

    /**
     * Resets the transfer phase to IDLE — call after the UI has acknowledged
     * COMPLETED, STOPPED, or FAILED.  Ready for a new backup run.
     */
    public void resetTransfer() {
        transferSent.postValue(0);
        transferTotal.postValue(0);
        failedCount.postValue(0);
        transferStatus.postValue(BackupTransferStatus.IDLE);
    }
}

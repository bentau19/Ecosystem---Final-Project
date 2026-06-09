package com.example.android.repositories;

import android.net.Uri;
import android.util.Log;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.domain.entities.BackupFileEntry;
import com.example.android.domain.enums.BackupScanStatus;
import com.example.android.domain.enums.BackupTransferStatus;

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
         * @param files Non-empty list of files to transfer.
         */
        void onTransferRequested(List<BackupFileEntry> files);
    }

    private ScanActionListener actionListener;
    private TransferActionListener transferActionListener;

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

    // ── Observers (for ViewModel / Fragment / ConnectivityService) ────────────

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

    // ── UI → Repository (called by Fragment / BackupViewModel) ───────────────

    /**
     * Initiates a scan — transitions IDLE → SCANNING and fires the action listener.
     *
     * @param mode      Backup mode constant from {@link com.example.android.domain.usecases.ScanBackupFilesUseCase}.
     * @param folderUri SAF tree URI; must be non-null when {@code mode == "folder"}.
     */
    public void requestScan(String mode, Uri folderUri) {
        Log.d(TAG, "requestScan: mode=" + mode);
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
     * succeeded.  SCANNING → READY.
     */
    public void onScanComplete(List<BackupFileEntry> files) {
        Log.d(TAG, "onScanComplete: " + files.size() + " files");
        scannedFiles.postValue(files);
        scanStatus.postValue(BackupScanStatus.READY);
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
     * (READY / FAILED).  Ready for the next scan.
     */
    public void reset() {
        scannedFiles.postValue(Collections.emptyList());
        scanStatus.postValue(BackupScanStatus.IDLE);
    }

    // ── Transfer: UI → Repository (called by BackupViewModel) ────────────────

    /**
     * Initiates a backup transfer — transitions IDLE → SENDING and fires the
     * transfer action listener so {@code ConnectivityService} can start the
     * background UseCase.
     *
     * @param files Non-empty scanned file list ready to send.
     */
    public void requestTransfer(List<BackupFileEntry> files) {
        if (files == null || files.isEmpty()) {
            Log.w(TAG, "requestTransfer called with empty list — ignoring");
            return;
        }
        Log.d(TAG, "requestTransfer: " + files.size() + " files");
        transferSent.postValue(0);
        transferTotal.postValue(files.size());
        transferStatus.postValue(BackupTransferStatus.SENDING);

        if (transferActionListener != null) {
            transferActionListener.onTransferRequested(files);
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
     * Resets the transfer phase to IDLE — call after the UI has acknowledged
     * COMPLETED or FAILED.  Ready for a new backup run.
     */
    public void resetTransfer() {
        transferSent.postValue(0);
        transferTotal.postValue(0);
        transferStatus.postValue(BackupTransferStatus.IDLE);
    }
}

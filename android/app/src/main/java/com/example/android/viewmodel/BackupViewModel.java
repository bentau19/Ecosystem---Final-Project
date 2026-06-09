package com.example.android.viewmodel;

import android.net.Uri;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.domain.entities.BackupFileEntry;
import com.example.android.domain.enums.BackupScanStatus;
import com.example.android.domain.enums.BackupTransferStatus;
import com.example.android.domain.usecases.ScanBackupFilesUseCase;
import com.example.android.repositories.BackupRepository;

import java.util.List;

/**
 * ViewModel for the backup feature.
 *
 * <p>Responsibilities:
 * <ul>
 *   <li>Exposes scan status and scanned file list as LiveData for
 *       {@link com.example.android.ui.fragments.BackupFragment} to observe.</li>
 *   <li>Translates user actions (Start Backup) into {@link BackupRepository} calls.</li>
 *   <li>Owns the background thread that runs {@link ScanBackupFilesUseCase}.</li>
 * </ul>
 *
 * <p>What this ViewModel does NOT do:
 * <ul>
 *   <li>Does not know about Android Context beyond what was injected at construction.</li>
 *   <li>Does not touch network / TauSync — that is the next phase (SendBackupManifest).</li>
 *   <li>Does not reference any Fragment or Activity.</li>
 * </ul>
 *
 * <p>Wired through {@link BackupViewModelFactory} (manual DI).
 */
public class BackupViewModel extends ViewModel {

    private static final String TAG = "BackupViewModel";

    private final BackupRepository repository;
    private final ScanBackupFilesUseCase scanUseCase;

    public BackupViewModel(BackupRepository repository,
                           ScanBackupFilesUseCase scanUseCase) {
        this.repository = repository;
        this.scanUseCase = scanUseCase;

        // Register this ViewModel as the ScanActionListener so that
        // BackupRepository.requestScan() can route back to us.
        repository.setActionListener((mode, folderUri) ->
                executeScanOnBackgroundThread(mode, folderUri));
    }

    // ── Scan observables ──────────────────────────────────────────────────────

    /**
     * @return Current scan lifecycle state; observe in Fragment to drive progress UI.
     */
    public LiveData<BackupScanStatus> getScanStatus() {
        return repository.getScanStatus();
    }

    /**
     * @return The list of scanned files; only populated when status is {@code READY}.
     */
    public LiveData<List<BackupFileEntry>> getScannedFiles() {
        return repository.getScannedFiles();
    }

    // ── Transfer observables ──────────────────────────────────────────────────

    /**
     * @return Current backup transfer lifecycle state; observe to drive in-app progress UI.
     */
    public LiveData<BackupTransferStatus> getTransferStatus() {
        return repository.getTransferStatus();
    }

    /**
     * @return Number of files successfully sent so far in the current batch.
     */
    public LiveData<Integer> getTransferSent() {
        return repository.getTransferSent();
    }

    /**
     * @return Total number of files in the current backup batch.
     */
    public LiveData<Integer> getTransferTotal() {
        return repository.getTransferTotal();
    }

    // ── User actions ──────────────────────────────────────────────────────────

    /**
     * Initiates a backup scan for the given mode.
     *
     * <p>Transitions the repository to SCANNING, then spawns a background thread
     * to run {@link ScanBackupFilesUseCase}.  Results are posted back via LiveData.
     *
     * @param mode      {@link ScanBackupFilesUseCase#MODE_ALL_MEDIA} or
     *                  {@link ScanBackupFilesUseCase#MODE_FOLDER}.
     * @param folderUri SAF tree URI — required when {@code mode == MODE_FOLDER};
     *                  pass {@code null} for {@code MODE_ALL_MEDIA}.
     */
    public void startScan(String mode, @Nullable Uri folderUri) {
        Log.d(TAG, "startScan: mode=" + mode);
        repository.requestScan(mode, folderUri);
        // requestScan fires actionListener → executeScanOnBackgroundThread
    }

    /**
     * Starts transferring the scanned file list to the connected PC.
     *
     * <p>Must be called after the scan reaches {@link BackupScanStatus#READY}.
     * Delegates to {@link BackupRepository#requestTransfer}, which fires the
     * {@code TransferActionListener} registered by {@code ConnectivityService}.
     * Progress is reported back via {@link #getTransferSent()} / {@link #getTransferTotal()}.
     */
    public void startTransfer() {
        List<BackupFileEntry> files = repository.getScannedFiles().getValue();
        if (files == null || files.isEmpty()) {
            Log.w(TAG, "startTransfer: no scanned files available");
            return;
        }
        Log.d(TAG, "startTransfer: " + files.size() + " files");
        repository.requestTransfer(files);
    }

    /**
     * Resets scan repository to IDLE — call after the Fragment has acknowledged the
     * terminal scan state (READY / FAILED) and is ready for the next scan.
     */
    public void reset() {
        repository.reset();
    }

    /**
     * Resets transfer repository to IDLE — call after the Fragment has acknowledged
     * COMPLETED or FAILED.
     */
    public void resetTransfer() {
        repository.resetTransfer();
    }

    // ── Private ───────────────────────────────────────────────────────────────

    /**
     * Spawns a daemon background thread to run the blocking scan UseCase.
     * Results are delivered to the repository via {@code postValue()} (thread-safe).
     *
     * <p>The scan is purely local (no TauSync), so {@code ConnectivityService}
     * is not involved.
     */
    private void executeScanOnBackgroundThread(String mode, @Nullable Uri folderUri) {
        new Thread(() -> {
            scanUseCase.execute(mode, folderUri, new ScanBackupFilesUseCase.ScanCallback() {
                @Override
                public void onScanComplete(java.util.List<BackupFileEntry> files) {
                    repository.onScanComplete(files);
                }

                @Override
                public void onScanFailed(Exception e) {
                    Log.e(TAG, "Scan failed: " + e.getMessage(), e);
                    repository.onScanFailed();
                }
            });
        }, "BackupScanThread").start();
    }

    @Override
    protected void onCleared() {
        super.onCleared();
        repository.setActionListener(null);
    }
}

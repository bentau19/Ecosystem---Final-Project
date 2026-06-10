package com.example.android.viewmodel;

import android.net.Uri;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.domain.entities.BackupFileEntry;
import com.example.android.domain.entities.BackupOptions;
import com.example.android.domain.enums.BackupScanStatus;
import com.example.android.domain.usecases.ScanBackupFilesUseCase;
import com.example.android.repositories.BackupRepository;

/**
 * ViewModel for the backup feature.
 *
 * <p>Responsibilities:
 * <ul>
 *   <li>Translates the user's Start Backup tap into a {@link BackupRepository} scan
 *       request — the repository owns the scan→transfer handoff and all progress
 *       state from this point on (see {@link BackupRepository#onScanComplete}).</li>
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

    // ── Observables (for Fragment) ────────────────────────────────────────────

    /**
     * Forwards the repository's scan-lifecycle LiveData so {@link
     * com.example.android.ui.fragments.BackupFragment} can observe it without
     * holding a direct reference to the repository.
     */
    public LiveData<BackupScanStatus> getScanStatus() {
        return repository.getScanStatus();
    }

    // ── User actions ──────────────────────────────────────────────────────────

    /**
     * Initiates a backup scan for the given mode.
     *
     * <p>Transitions the repository to SCANNING, then spawns a background thread
     * to run {@link ScanBackupFilesUseCase}.  When the scan completes, the
     * repository itself auto-triggers the transfer phase using {@code options}
     * (see {@link BackupRepository#onScanComplete}) — the Fragment that called
     * this method has typically already returned to the main screen by then.
     *
     * @param mode      {@link ScanBackupFilesUseCase#MODE_ALL_MEDIA} or
     *                  {@link ScanBackupFilesUseCase#MODE_FOLDER}.
     * @param folderUri SAF tree URI — required when {@code mode == MODE_FOLDER};
     *                  pass {@code null} for {@code MODE_ALL_MEDIA}.
     * @param options   User-configured backup options, forwarded to the transfer
     *                  phase once the scan finishes.
     */
    public void startScan(String mode, @Nullable Uri folderUri, BackupOptions options) {
        Log.d(TAG, "startScan: mode=" + mode + " options=" + options);
        repository.requestScan(mode, folderUri, options);
        // requestScan fires actionListener → executeScanOnBackgroundThread
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

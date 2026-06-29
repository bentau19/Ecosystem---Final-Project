package com.example.android.viewmodel;

import android.app.Application;
import android.content.Intent;

import androidx.annotation.NonNull;
import androidx.lifecycle.AndroidViewModel;
import androidx.lifecycle.LiveData;

import com.example.android.repositories.SettingsRepository;
import com.example.android.services.ConnectivityService;

/**
 * ViewModel for {@link com.example.android.ui.fragments.SettingsFragment}.
 *
 * <p>Responsibilities:
 * <ul>
 *   <li>Exposes {@link LiveData} from {@link SettingsRepository} so the Fragment can
 *       observe settings changes — including those pushed by the connected PC.</li>
 *   <li>Persists user changes via the repository.</li>
 *   <li>Triggers {@code ACTION_PUSH_SETTINGS} on {@link ConnectivityService} after a
 *       Virtual Drive toggle so the PC is notified immediately (if connected).
 *       The Service is a no-op if it is not currently running.</li>
 * </ul>
 *
 * <p>Extends {@link AndroidViewModel} to access {@link Application} for starting the
 * Service intent — no other Android context usage.
 *
 * <p>Created with the built-in {@link androidx.lifecycle.ViewModelProvider.AndroidViewModelFactory}
 * (no custom factory needed):
 * <pre>{@code
 *   settingsViewModel = new ViewModelProvider(this).get(SettingsViewModel.class);
 * }</pre>
 */
public class SettingsViewModel extends AndroidViewModel {

    /** Service action that triggers a settings push to the PC. */
    public static final String ACTION_PUSH_SETTINGS = "com.example.android.ACTION_PUSH_SETTINGS";

    private final SettingsRepository repository;

    public SettingsViewModel(@NonNull Application application) {
        super(application);
        repository = SettingsRepository.getInstance(application.getApplicationContext());
    }

    // ── Observables ───────────────────────────────────────────────────────────

    /**
     * Virtual Drive enabled state. Observed by the Fragment to keep the switch in sync
     * when the PC pushes a state change.
     */
    public LiveData<Boolean> getVirtualDriveEnabled() {
        return repository.getVirtualDriveEnabledLiveData();
    }

    /**
     * Clipboard sync enabled state. Observed by the Fragment; also updated when the PC
     * pushes its clipboard state via {@link com.example.android.network.handlers.SettingsChannelHandler}.
     */
    public LiveData<Boolean> getClipboardEnabled() {
        return repository.getClipboardEnabledLiveData();
    }

    /**
     * Webcam mirroring enabled state. Observed by the Fragment; also updated when the PC
     * pushes its webcam state.
     */
    public LiveData<Boolean> getWebcamEnabled() {
        return repository.getWebcamEnabledLiveData();
    }

    /**
     * File Backup enabled state. Phone-local — not synced to the PC.
     */
    public LiveData<Boolean> getBackupEnabled() {
        return repository.getBackupEnabledLiveData();
    }

    /**
     * Auto-launch preference. No remote sync (auto-launch is phone-only).
     */
    public LiveData<Boolean> getAutoLaunch() {
        return repository.getAutoLaunchLiveData();
    }

    // ── Synchronous reads (used for initial switch state before observers fire) ─

    public boolean isVirtualDriveEnabled() {
        return repository.isVirtualDriveEnabled();
    }

    public boolean isClipboardEnabled() {
        return repository.isClipboardEnabled();
    }

    public boolean isWebcamEnabled() {
        return repository.isWebcamEnabled();
    }

    public boolean isBackupEnabled() {
        return repository.isBackupEnabled();
    }

    public boolean isAutoLaunch() {
        return repository.isAutoLaunch();
    }

    // ── User actions ──────────────────────────────────────────────────────────

    /**
     * Persists the Virtual Drive toggle and asks the Service to push all tool states
     * to the connected PC. Safe to call when the Service is not running — silently discarded.
     */
    public void setVirtualDriveEnabled(boolean enabled) {
        repository.setVirtualDriveEnabled(enabled);
        pushSettingsToService();
    }

    /**
     * Persists the clipboard-sync toggle and asks the Service to push all tool states
     * to the connected PC.
     */
    public void setClipboardEnabled(boolean enabled) {
        repository.setClipboardEnabled(enabled);
        pushSettingsToService();
    }

    /**
     * Persists the webcam toggle and asks the Service to push all tool states
     * to the connected PC.
     */
    public void setWebcamEnabled(boolean enabled) {
        repository.setWebcamEnabled(enabled);
        pushSettingsToService();
    }

    /**
     * Persists the file-backup toggle and pushes all tool states to the connected PC.
     * The PC will update its own backup setting and reflect it in the Settings UI.
     */
    public void setBackupEnabled(boolean enabled) {
        repository.setBackupEnabled(enabled);
        pushSettingsToService();
    }

    /**
     * Persists the auto-launch preference and enables/disables {@link
     * com.example.android.services.BootReceiver} via the repository.
     */
    public void setAutoLaunch(boolean enabled) {
        repository.setAutoLaunch(enabled);
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    /**
     * Sends {@code ACTION_PUSH_SETTINGS} to {@link ConnectivityService} so it can push
     * all three tool-enabled states to the connected PC in one payload.
     * No-op if the Service is not currently running.
     */
    private void pushSettingsToService() {
        Intent intent = new Intent(getApplication(), ConnectivityService.class);
        intent.setAction(ACTION_PUSH_SETTINGS);
        getApplication().startService(intent);
    }
}

package com.example.android.repositories;

import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.services.BootReceiver;

/**
 * Persists app-level settings in {@link SharedPreferences} and exposes them as
 * {@link LiveData} so Fragments can react to changes — including those pushed by
 * the connected PC via {@link com.example.android.network.handlers.SettingsChannelHandler}.
 *
 * <h3>Settings</h3>
 * <ul>
 *   <li><b>Auto-launch</b> — start {@link com.example.android.services.ConnectivityService}
 *       on device boot. Toggling enables/disables {@link BootReceiver} via
 *       {@link PackageManager#setComponentEnabledSetting}.</li>
 *   <li><b>Virtual Drive enabled</b> — whether the Virtual Drive tool is shown in the
 *       actions dashboard and its state is synced to the connected PC.</li>
 * </ul>
 *
 * <h3>Thread-safety</h3>
 * {@link MutableLiveData#postValue} is used throughout so this class is safe to call
 * from background threads (e.g. {@link com.example.android.network.handlers.SettingsChannelHandler}
 * running on {@code PeerRequestHandlerThread}).
 */
public class SettingsRepository {

    // ── SharedPreferences keys ────────────────────────────────────────────────

    private static final String PREFS_NAME            = "syncdose_settings";
    private static final String KEY_AUTO_LAUNCH        = "auto_launch";
    private static final String KEY_VIRTUAL_DRIVE      = "virtual_drive_enabled";
    private static final String KEY_CLIPBOARD_ENABLED  = "clipboard_enabled";
    private static final String KEY_WEBCAM_ENABLED     = "webcam_enabled";
    private static final String KEY_BACKUP_ENABLED     = "backup_enabled";

    // ── Singleton ─────────────────────────────────────────────────────────────

    private static SettingsRepository instance;

    /**
     * Returns or creates the singleton, using {@code context} to open SharedPreferences
     * and register the BootReceiver reference. Safe to call multiple times — only the
     * first call initializes.
     */
    public static synchronized SettingsRepository getInstance(Context context) {
        if (instance == null) {
            instance = new SettingsRepository(context.getApplicationContext());
        }
        return instance;
    }

    /**
     * Returns the already-initialized singleton.
     *
     * @throws IllegalStateException if {@link #getInstance(Context)} has not been called yet.
     */
    public static SettingsRepository getInstance() {
        if (instance == null) {
            throw new IllegalStateException(
                    "SettingsRepository not initialized — call getInstance(Context) first");
        }
        return instance;
    }

    // ── State ─────────────────────────────────────────────────────────────────

    private final Context appContext;
    private final SharedPreferences prefs;

    private final MutableLiveData<Boolean> virtualDriveEnabled = new MutableLiveData<>();
    private final MutableLiveData<Boolean> autoLaunch          = new MutableLiveData<>();
    private final MutableLiveData<Boolean> clipboardEnabled    = new MutableLiveData<>();
    private final MutableLiveData<Boolean> webcamEnabled       = new MutableLiveData<>();
    private final MutableLiveData<Boolean> backupEnabled       = new MutableLiveData<>();

    private SettingsRepository(Context appContext) {
        this.appContext = appContext;
        prefs = appContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        // Hydrate LiveData with persisted values on startup. Every setting defaults to
        // true (opt-out) so a fresh install has all tools — and auto-launch — enabled,
        // matching the desktop SettingsDTO.
        virtualDriveEnabled.setValue(prefs.getBoolean(KEY_VIRTUAL_DRIVE, true));
        autoLaunch.setValue(prefs.getBoolean(KEY_AUTO_LAUNCH, true));
        clipboardEnabled.setValue(prefs.getBoolean(KEY_CLIPBOARD_ENABLED, true));
        webcamEnabled.setValue(prefs.getBoolean(KEY_WEBCAM_ENABLED, true));
        backupEnabled.setValue(prefs.getBoolean(KEY_BACKUP_ENABLED, true));

        // Reconcile the BootReceiver component with the persisted/default auto-launch
        // value. The receiver is android:enabled="false" in the manifest, so a fresh
        // install with auto-launch defaulting ON needs this to actually arm boot start.
        // Idempotent and safe from any entry point (including BootReceiver itself).
        applyBootReceiverState(prefs.getBoolean(KEY_AUTO_LAUNCH, true));
    }

    // ── Virtual Drive ─────────────────────────────────────────────────────────

    /** Current persisted value — safe to call from any thread. */
    public boolean isVirtualDriveEnabled() {
        return prefs.getBoolean(KEY_VIRTUAL_DRIVE, true);
    }

    /** Observed by {@link com.example.android.ui.fragments.SettingsFragment}. */
    public LiveData<Boolean> getVirtualDriveEnabledLiveData() {
        return virtualDriveEnabled;
    }

    /**
     * Persists and broadcasts the new Virtual Drive state.
     * Safe to call from background threads (uses {@code postValue}).
     *
     * <p>Call this from <em>user interaction</em> (SettingsViewModel). After calling
     * this, trigger {@code ACTION_PUSH_SETTINGS} on {@link com.example.android.services.ConnectivityService}
     * to sync the change to the PC.
     */
    public void setVirtualDriveEnabled(boolean enabled) {
        prefs.edit().putBoolean(KEY_VIRTUAL_DRIVE, enabled).apply();
        virtualDriveEnabled.postValue(enabled);
    }

    /**
     * Same as {@link #setVirtualDriveEnabled(boolean)} but called by
     * {@link com.example.android.network.handlers.SettingsChannelHandler} when the PC
     * pushes its state. Does NOT trigger a return-push to avoid a sync loop.
     *
     * <p>Semantically identical in this implementation — the "no return push" guarantee
     * is enforced by the Fragment's {@code programmaticUpdate} flag, but having a
     * distinct method name makes the intent explicit in the handler code.
     */
    public void setVirtualDriveEnabledFromPc(boolean enabled) {
        prefs.edit().putBoolean(KEY_VIRTUAL_DRIVE, enabled).apply();
        virtualDriveEnabled.postValue(enabled);
    }

    // ── Auto-launch ───────────────────────────────────────────────────────────

    /** Current persisted value — safe to call from any thread. */
    public boolean isAutoLaunch() {
        return prefs.getBoolean(KEY_AUTO_LAUNCH, true);
    }

    /** Observed by {@link com.example.android.ui.fragments.SettingsFragment}. */
    public LiveData<Boolean> getAutoLaunchLiveData() {
        return autoLaunch;
    }

    /**
     * Persists the auto-launch preference and enables or disables {@link BootReceiver}
     * via {@link PackageManager#setComponentEnabledSetting}.
     *
     * <p>Enabling makes Android call {@code BootReceiver.onReceive()} after every
     * device restart so the app re-connects automatically. Disabling is the default
     * ({@code android:enabled="false"} in the manifest).
     */
    public void setAutoLaunch(boolean enabled) {
        prefs.edit().putBoolean(KEY_AUTO_LAUNCH, enabled).apply();
        autoLaunch.postValue(enabled);
        applyBootReceiverState(enabled);
    }

    /**
     * Enables or disables {@link BootReceiver} via
     * {@link PackageManager#setComponentEnabledSetting} to match {@code enabled}.
     *
     * <p>Shared by {@link #setAutoLaunch(boolean)} (user toggle) and the constructor
     * (startup reconcile). Idempotent — calling it repeatedly with the same value is a
     * no-op. The receiver is {@code android:enabled="false"} in the manifest, so this is
     * what actually arms boot-start when auto-launch is on (including the first run, when
     * it defaults ON).
     */
    private void applyBootReceiverState(boolean enabled) {
        ComponentName receiver = new ComponentName(appContext, BootReceiver.class);
        int newState = enabled
                ? PackageManager.COMPONENT_ENABLED_STATE_ENABLED
                : PackageManager.COMPONENT_ENABLED_STATE_DISABLED;
        appContext.getPackageManager()
                .setComponentEnabledSetting(receiver, newState, PackageManager.DONT_KILL_APP);
    }

    // ── Clipboard Sync ────────────────────────────────────────────────────────

    /** Current persisted value — safe to call from any thread. */
    public boolean isClipboardEnabled() {
        return prefs.getBoolean(KEY_CLIPBOARD_ENABLED, true);
    }

    /** Observed by {@link com.example.android.ui.fragments.SettingsFragment}. */
    public LiveData<Boolean> getClipboardEnabledLiveData() {
        return clipboardEnabled;
    }

    /**
     * Persists and broadcasts the new clipboard-sync state.
     * Call this from user interaction (SettingsViewModel). After calling this,
     * trigger {@code ACTION_PUSH_SETTINGS} on ConnectivityService to sync the change to the PC.
     */
    public void setClipboardEnabled(boolean enabled) {
        prefs.edit().putBoolean(KEY_CLIPBOARD_ENABLED, enabled).apply();
        clipboardEnabled.postValue(enabled);
    }

    /**
     * Called by {@link com.example.android.network.handlers.SettingsChannelHandler} when the PC
     * pushes its clipboard state. Does NOT trigger a return-push — loop prevention is handled
     * by the Fragment's {@code programmaticUpdate} flag.
     */
    public void setClipboardEnabledFromPc(boolean enabled) {
        prefs.edit().putBoolean(KEY_CLIPBOARD_ENABLED, enabled).apply();
        clipboardEnabled.postValue(enabled);
    }

    // ── Webcam ────────────────────────────────────────────────────────────────

    /** Current persisted value — safe to call from any thread. */
    public boolean isWebcamEnabled() {
        return prefs.getBoolean(KEY_WEBCAM_ENABLED, true);
    }

    /** Observed by {@link com.example.android.ui.fragments.SettingsFragment}. */
    public LiveData<Boolean> getWebcamEnabledLiveData() {
        return webcamEnabled;
    }

    /**
     * Persists and broadcasts the new webcam state.
     * After calling this, trigger {@code ACTION_PUSH_SETTINGS} to sync to the PC.
     */
    public void setWebcamEnabled(boolean enabled) {
        prefs.edit().putBoolean(KEY_WEBCAM_ENABLED, enabled).apply();
        webcamEnabled.postValue(enabled);
    }

    /**
     * Called by {@link com.example.android.network.handlers.SettingsChannelHandler} when the PC
     * pushes its webcam state. Does NOT trigger a return-push.
     */
    public void setWebcamEnabledFromPc(boolean enabled) {
        prefs.edit().putBoolean(KEY_WEBCAM_ENABLED, enabled).apply();
        webcamEnabled.postValue(enabled);
    }

    // ── File Backup ───────────────────────────────────────────────────────────

    /**
     * Current persisted value — safe to call from any thread.
     * Phone-local: not synced to the PC (no {@code FromPc} variant).
     */
    public boolean isBackupEnabled() {
        return prefs.getBoolean(KEY_BACKUP_ENABLED, true);
    }

    /** Observed by {@link com.example.android.ui.fragments.SettingsFragment}. */
    public LiveData<Boolean> getBackupEnabledLiveData() {
        return backupEnabled;
    }

    /** Persists and broadcasts the new backup enabled state. */
    public void setBackupEnabled(boolean enabled) {
        prefs.edit().putBoolean(KEY_BACKUP_ENABLED, enabled).apply();
        backupEnabled.postValue(enabled);
    }

    /**
     * Called by {@link com.example.android.network.handlers.SettingsChannelHandler} when the PC
     * pushes its backup state. Does NOT trigger a return-push — loop prevention is handled
     * by the Fragment's {@code programmaticUpdate} flag.
     *
     * <p>Semantically identical to {@link #setBackupEnabled(boolean)} in this implementation;
     * the distinct method name makes the call-site intent explicit in the handler code.
     */
    public void setBackupEnabledFromPc(boolean enabled) {
        prefs.edit().putBoolean(KEY_BACKUP_ENABLED, enabled).apply();
        backupEnabled.postValue(enabled);
    }
}

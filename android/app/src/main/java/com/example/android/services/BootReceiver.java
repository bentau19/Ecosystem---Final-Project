package com.example.android.services;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

import androidx.core.content.ContextCompat;

import com.example.android.repositories.SettingsRepository;

/**
 * Starts {@link ConnectivityService} automatically after device reboot when the
 * user has enabled <em>Launch on startup</em> in Settings.
 *
 * <h3>Enabled / disabled lifecycle</h3>
 * This receiver is declared in the manifest with {@code android:enabled="false"} so it
 * has zero impact by default. {@link SettingsRepository#setAutoLaunch(boolean)} toggles
 * it via {@link android.content.pm.PackageManager#setComponentEnabledSetting} at runtime.
 *
 * <h3>What it starts</h3>
 * {@link ConnectivityService} is started as a foreground service. If no saved
 * connection parameters are available (first boot after install, or after the device
 * was forgotten), the service will start, find no target IP/MAC, and stop itself
 * gracefully — no crash, no visible effect.
 *
 * <h3>Permissions</h3>
 * Requires {@code android.permission.RECEIVE_BOOT_COMPLETED} (declared in manifest).
 */
public class BootReceiver extends BroadcastReceiver {

    private static final String TAG = "BootReceiver";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            return; // guard against unexpected intents
        }

        Log.d(TAG, "Device booted — checking auto-launch setting");

        // Initialize SettingsRepository with a context so we can read the preference.
        SettingsRepository settings = SettingsRepository.getInstance(context);
        if (!settings.isAutoLaunch()) {
            // Shouldn't happen (receiver is disabled when toggle is off), but defensive.
            Log.d(TAG, "Auto-launch is off — skipping service start");
            return;
        }

        Log.d(TAG, "Auto-launch is on — starting ConnectivityService");

        // Start the service. Without TARGET_IP or TARGET_MAC extras the service will
        // detect the missing parameters and call stopSelf() immediately — this is the
        // safe idle state until the user manually connects at least once per session.
        //
        // A future enhancement could persist the last-used connection parameters in
        // SettingsRepository so the service can reconnect fully automatically.
        Intent serviceIntent = new Intent(context, ConnectivityService.class);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ContextCompat.startForegroundService(context, serviceIntent);
        } else {
            context.startService(serviceIntent);
        }
    }
}

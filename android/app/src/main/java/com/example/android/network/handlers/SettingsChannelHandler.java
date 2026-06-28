package com.example.android.network.handlers;

import android.util.Log;

import com.example.android.enums.SettingsChannels;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.SettingsRepository;

import org.json.JSONObject;

/**
 * Handles incoming tool-enabled state pushes from the connected PC.
 *
 * <p>Registered in
 * {@link com.example.android.services.ConnectivityService#registerChannelHandlers()}
 * under {@code settings_tools_pc_to_android}. The PC opens this channel whenever
 * its tool settings change (e.g., Virtual Drive toggled from the desktop UI).
 *
 * <h3>Wire format</h3>
 * <pre>{"virtualDrive": true, "clipboard": true, "webcam": true}</pre>
 * Parsed with {@code optBoolean} so absent fields fall back to the current persisted
 * value — forward-compatible with a PC that doesn't yet send all three fields.
 *
 * <h3>Loop prevention</h3>
 * This handler calls {@link SettingsRepository#setVirtualDriveEnabledFromPc} —
 * a method that persists the value and posts LiveData but does NOT trigger
 * {@code ACTION_PUSH_SETTINGS} back to the Service. The Fragment's
 * {@code programmaticUpdate} flag then suppresses the switch listener, ensuring
 * no return-push is fired.
 */
public class SettingsChannelHandler implements ChannelHandler {

    private static final String TAG = "SettingsChannelHandler";

    private final TransportManager transportManager;
    private final SettingsRepository settingsRepository;

    public SettingsChannelHandler(TransportManager transportManager,
                                  SettingsRepository settingsRepository) {
        this.transportManager    = transportManager;
        this.settingsRepository  = settingsRepository;
    }

    @Override
    public String getChannelName() {
        return SettingsChannels.TOOLS_PC_TO_ANDROID.getValue();
    }

    /**
     * Called by the polling loop on {@code PeerRequestHandlerThread} when the PC has
     * opened {@code settings_tools_pc_to_android}.
     *
     * <p>Reads the JSON payload, applies each field to {@link SettingsRepository},
     * and returns. LiveData observers in {@link com.example.android.ui.fragments.SettingsFragment}
     * (if currently visible) will update the UI automatically.
     */
    @Override
    public void onPeerRequest() {
        try {
            String raw = transportManager.readFromChannel(
                    SettingsChannels.TOOLS_PC_TO_ANDROID.getValue()
            );

            if (raw == null || raw.isEmpty()) {
                Log.w(TAG, "Received empty settings payload from PC — ignoring");
                return;
            }

            JSONObject payload = new JSONObject(raw);

            // Each field falls back to the current persisted value so an absent field is a no-op
            // — forward-compatible with a PC that doesn't yet send all four fields.
            boolean vd = payload.optBoolean("virtualDrive",
                    settingsRepository.isVirtualDriveEnabled());
            boolean cb = payload.optBoolean("clipboard",
                    settingsRepository.isClipboardEnabled());
            boolean wc = payload.optBoolean("webcam",
                    settingsRepository.isWebcamEnabled());
            boolean bk = payload.optBoolean("backup",
                    settingsRepository.isBackupEnabled());

            settingsRepository.setVirtualDriveEnabledFromPc(vd);
            settingsRepository.setClipboardEnabledFromPc(cb);
            settingsRepository.setWebcamEnabledFromPc(wc);
            settingsRepository.setBackupEnabledFromPc(bk);

            Log.d(TAG, "Settings received from PC: virtualDrive=" + vd
                    + ", clipboard=" + cb + ", webcam=" + wc + ", backup=" + bk);

        } catch (Exception e) {
            Log.e(TAG, "Failed to receive settings from PC: " + e.getMessage());
        }
    }

    @Override
    public void onShutdown() {
        Log.d(TAG, "SettingsChannelHandler shut down");
    }
}

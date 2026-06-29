package com.example.android.domain.usecases;

import android.util.Log;

import com.example.android.enums.SettingsChannels;
import com.example.android.network.transport.TransportManager;

import org.json.JSONObject;

/**
 * Pushes the phone's current tool-enabled state to the connected PC.
 *
 * <p>Must be called from a background thread — {@link TransportManager#writeToChannel}
 * performs synchronous network I/O.
 *
 * <p>Wire format (matches the PC-side settings handler):
 * <pre>{"virtualDrive": true, "clipboard": true, "webcam": true}</pre>
 *
 * <p>All three fields are sent together so the receiver always has a complete picture.
 * The PC side uses permissive JSON parsing ({@code payload.get(key, current)}) to stay
 * compatible with older phone builds that may omit a field.
 *
 * <p>This use-case is instantiated once by
 * {@link com.example.android.services.ConnectivityService} and reused across the
 * connection lifetime. It is safe to call concurrently (the transport layer serializes
 * writes internally) but in practice only one push fires at a time.
 */
public class SettingsUseCase {

    private static final String TAG = "SettingsUseCase";

    private final TransportManager transportManager;

    public SettingsUseCase(TransportManager transportManager) {
        this.transportManager = transportManager;
    }

    /**
     * Sends the current tool-enabled state to the PC.
     *
     * @param virtualDriveEnabled {@code true} if the Virtual Drive tool is enabled.
     * @param clipboardEnabled    {@code true} if clipboard sync is enabled.
     * @param webcamEnabled       {@code true} if webcam mirroring is enabled.
     * @param backupEnabled       {@code true} if backup sessions are allowed.
     * @param darkModeEnabled     {@code true} if dark mode is active.
     */
    public void pushToolsState(boolean virtualDriveEnabled,
                               boolean clipboardEnabled,
                               boolean webcamEnabled,
                               boolean backupEnabled,
                               boolean darkModeEnabled) {
        try {
            JSONObject payload = new JSONObject();
            payload.put("virtualDrive", virtualDriveEnabled);
            payload.put("clipboard",    clipboardEnabled);
            payload.put("webcam",       webcamEnabled);
            payload.put("backup",       backupEnabled);
            payload.put("darkMode",     darkModeEnabled);

            Log.d(TAG, "Pushing tool state to PC: virtualDrive=" + virtualDriveEnabled
                    + ", clipboard=" + clipboardEnabled + ", webcam=" + webcamEnabled
                    + ", backup=" + backupEnabled + ", darkMode=" + darkModeEnabled);
            transportManager.writeToChannel(
                    SettingsChannels.TOOLS_ANDROID_TO_PC.getValue(),
                    payload.toString()
            );
            Log.d(TAG, "Tool state pushed successfully");

        } catch (Exception e) {
            Log.e(TAG, "Failed to push tool state: " + e.getMessage());
        }
    }
}

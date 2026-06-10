package com.example.android.network.handlers;

import android.util.Log;

import com.example.android.domain.usecases.BackupTransferUseCase;
import com.example.android.enums.BackupChannels;
import com.example.android.network.transport.TransportManager;

import org.json.JSONObject;

/**
 * Handles PC-originated backup control commands on {@link BackupChannels#BACKUP_CONTROL_FROM_PC}.
 *
 * <p>The PC calls {@code connect("backup_ctrl_pc")} once per command. The transport's
 * peer-request polling detects the connection, fires {@code onPeerRequestsAvailable}, and
 * the registry dispatches here. Each invocation of {@link #onPeerRequest()} reads one
 * {@code {"cmd": "pause"|"resume"|"stop"}} payload and forwards it to the running
 * {@link BackupTransferUseCase}.
 *
 * <p>This handler is registered once at service startup and remains in the registry for
 * the lifetime of the connection. If the PC sends a command when no transfer is active,
 * the forwarded call to the UseCase is a safe no-op (stop/pause/resume all guard against
 * being called outside an active session).
 */
public class BackupControlChannelHandler implements ChannelHandler {

    private static final String TAG = "BackupControlHandler";

    private final TransportManager transportManager;
    private final BackupTransferUseCase backupTransferUseCase;

    public BackupControlChannelHandler(TransportManager transportManager,
                                       BackupTransferUseCase backupTransferUseCase) {
        this.transportManager = transportManager;
        this.backupTransferUseCase = backupTransferUseCase;
    }

    @Override
    public String getChannelName() {
        return BackupChannels.BACKUP_CONTROL_FROM_PC.getValue();
    }

    @Override
    public void onPeerRequest() {
        try {
            String raw = transportManager.readFromChannel(
                    BackupChannels.BACKUP_CONTROL_FROM_PC.getValue());
            if (raw == null || raw.isEmpty()) return;

            JSONObject cmd = new JSONObject(raw);
            String cmdStr = cmd.getString("cmd");
            Log.d(TAG, "Control command from PC: " + cmdStr);

            switch (cmdStr) {
                case "pause":  backupTransferUseCase.pauseTransfer();  break;
                case "resume": backupTransferUseCase.resumeTransfer(); break;
                case "stop":   backupTransferUseCase.stopTransfer();   break;
                default:       Log.w(TAG, "Unknown control command: " + cmdStr);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error handling backup control command: " + e.getMessage(), e);
        }
    }

    @Override
    public void onShutdown() {
        Log.d(TAG, "BackupControlChannelHandler shut down");
    }
}

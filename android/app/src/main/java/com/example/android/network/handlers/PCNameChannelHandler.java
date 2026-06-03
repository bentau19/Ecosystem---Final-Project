package com.example.android.network.handlers;

import android.util.Log;

import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.enums.DeviceInfoChannels;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.DeviceRepository;

/**
 * PCNameChannelHandler handles PC name requests and updates.
 *
 * When the PC sends its name:
 * 1. Read PC name from the channel
 * 2. Update the repository with the PC name
 * 3. Notify all observers (UI) of the update
 */
public class PCNameChannelHandler implements ChannelHandler {

    private static final String TAG = "PCNameHandler";
    private final DeviceRepository repository;
    private final TransportManager transportManager;

    public PCNameChannelHandler(DeviceRepository repository, TransportManager transportManager) {
        this.repository = repository;
        this.transportManager = transportManager;
    }

    @Override
    public String getChannelName() {
        return DeviceInfoChannels.PC_NAME.getValue();
    }

    @Override
    public void onPeerRequest() {
        try {
            String pcName = transportManager.readFromChannel(DeviceInfoChannels.PC_NAME.getValue());
            Log.d(TAG, "Raw PC name from channel: '" + pcName + "'");
            
            if (pcName != null && !pcName.isEmpty()) {
                Log.d(TAG, "PC name received: " + pcName);

                // Update the repository with the PC name
                if (repository.getCurrentConnectionState() != null &&
                    repository.getCurrentConnectionState().getRemotePC() != null) {
                    RemoteDeviceInfo pc = repository.getCurrentConnectionState().getRemotePC();
                    Log.d(TAG, "Old PC name: " + pc.getPcName());
                    pc.setPcName(pcName);
                    Log.d(TAG, "New PC name set to: " + pc.getPcName());
                    repository.notifyStatusChanged();  // Notify observers of the change
                    Log.d(TAG, "Repository notification sent");
                } else {
                    Log.w(TAG, "RemotePC object is null, cannot update PC name");
                }
            } else {
                Log.w(TAG, "PC name is empty or null");
            }
        } catch (Exception e) {
            Log.e(TAG, "Error handling PC name request: " + e.getMessage());
            e.printStackTrace();
        }
    }

    @Override
    public void onShutdown() {
        Log.d(TAG, "PC name handler shut down");
    }
}


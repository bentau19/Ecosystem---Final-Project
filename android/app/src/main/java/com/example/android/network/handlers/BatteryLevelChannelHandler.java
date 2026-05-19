package com.example.android.network.handlers;

import android.util.Log;
import com.example.android.data.datasource.SystemDataSource;
import com.example.android.enums.DeviceInfoChannels;
import com.example.android.network.transport.TransportManager;

/**
 * BatteryLevelChannelHandler handles battery level requests from the PC.
 *
 * When the PC requests battery level:
 * 1. Read current battery from SystemDataSource
 * 2. Write it to the channel
 * 3. Update the repository if needed
 */
public class BatteryLevelChannelHandler implements ChannelHandler {

    private static final String TAG = "BatteryHandler";
    private final SystemDataSource systemDataSource;
    private final TransportManager transportManager;

    public BatteryLevelChannelHandler(SystemDataSource systemDataSource, TransportManager transportManager) {
        this.systemDataSource = systemDataSource;
        this.transportManager = transportManager;
    }

    @Override
    public String getChannelName() {
        return DeviceInfoChannels.BATTERY_LEVEL.getValue();
    }

    @Override
    public void onPeerRequest() {
        try {
            int batteryPercentage = systemDataSource.getBattery();
            transportManager.writeToChannel(
                    DeviceInfoChannels.BATTERY_LEVEL.getValue(),
                    String.valueOf(batteryPercentage)
            );
            Log.d(TAG, "Battery level sent: " + batteryPercentage + "%");
        } catch (Exception e) {
            Log.e(TAG, "Error handling battery level request: " + e.getMessage());
        }
    }

    @Override
    public void onShutdown() {
        Log.d(TAG, "Battery level handler shut down");
    }
}


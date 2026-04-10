package com.example.android.viewmodel;

import android.content.Context;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.data.models.entities.DeviceConnectionState;
import com.example.android.data.models.entities.DeviceStorageStats;
import com.example.android.data.models.entities.RemoteDeviceInfo;
import com.example.android.data.models.enums.ConnectionType;
import com.example.android.data.repositories.DeviceRepository;
import com.example.android.data.serializers.DeviceSerializer;
import com.example.android.utils.DeviceUtils;
import com.example.android.utils.NetworkUtils;

/**
 * ViewModel responsible for preparing and managing data for the UI.
 * It acts as a bridge between the DeviceRepository and the Fragments,
 * handling business logic such as QR data processing and status refreshing.
 */
public class MainViewModel extends ViewModel {

    private final DeviceRepository repository = DeviceRepository.getInstance();
    private android.content.BroadcastReceiver batteryReceiver;

    /**
     * @return LiveData containing the unified connection state (Local device + Remote PC).
     */
    public LiveData<DeviceConnectionState> getConnectionState() {
        return repository.getConnectionState();
    }

    /**
     * Refreshes local hardware statistics such as battery level and IP address.
     * Updates the repository which in turn notifies the UI observers.
     * @param context Application context for system services access.
     */
    public void refreshLocalDeviceStats(Context context) {
        String currentPhoneIp = NetworkUtils.getLocalIpAddress(context);
        int battery = DeviceUtils.getBatteryPercentage(context);

        // Update the repository with fresh local data
        repository.updateLocalIp(currentPhoneIp);
        repository.updateLocalBattery(battery);

        // Future implementation for storage updates can be added here
        // long total = DeviceUtils.getTotalStorage();
        // long available = DeviceUtils.getAvailableStorage();
        // repository.updateLocalStorage(total, available);
    }

    /**
     * Processes raw QR data and initiates the connection sequence.
     * @param context Context for refreshing stats before connecting.
     * @param qrData The raw string retrieved from the QR scanner.
     * @return true if the connection data was valid and initiated; false otherwise.
     */
    public boolean handleConnectionFromQR(Context context, String qrData) {
        // 1. Logic for deserializing the QR data into a RemoteDeviceInfo object
        // DeviceSerializer serializer = new DeviceSerializer();
        // RemoteDeviceInfo remote = serializer.deserializeRemoteInfo(qrData);

        // Mock implementation for development purposes:
        String pcName = "Ben-PC";
        String pcIp = "192.168.1.15";
        ConnectionType type = ConnectionType.WIFI;

        // Basic validation of the IP address
        if (pcIp == null || pcIp.equals("0.0.0.0")) {
            return false;
        }

        // 2. Ensure local stats are fresh before establishing a remote session
        refreshLocalDeviceStats(context);

        // 3. Execute the connection via the repository
        repository.connect(pcName, pcIp, type);
        return true;
    }

    /**
     * Commands the repository to terminate the current remote session.
     */
    public void disconnectFromPc() {
        repository.disconnect();
    }

    /**
     * Fetches the latest storage statistics from the repository.
     * @return DeviceStorageStats containing formatted status and usage percentage.
     */
    public DeviceStorageStats getStorageStats() {
        return repository.getLocalDeviceStorage();
    }

    /**
     * NOTE:
     * Currently, battery monitoring is handled within the ViewModel for UI demonstration purposes.
     * In the next phase, this logic will be migrated to a Foreground Service (ConnectionService).
     * This migration will ensure continuous monitoring and data synchronization with the PC
     * even when the app is in the background or the screen is off.
     */
    public void startBatteryMonitoring(Context context) {
        if (batteryReceiver != null) return;

        batteryReceiver = new android.content.BroadcastReceiver() {
            @Override
            public void onReceive(Context context, android.content.Intent intent) {
                int level = intent.getIntExtra(android.os.BatteryManager.EXTRA_LEVEL, -1);
                int scale = intent.getIntExtra(android.os.BatteryManager.EXTRA_SCALE, -1);
                int batteryPct = (int) ((level / (float) scale) * 100);

                // update the local battery level in the repository
                repository.updateLocalBattery(batteryPct);
            }
        };

        context.registerReceiver(batteryReceiver,
                new android.content.IntentFilter(android.content.Intent.ACTION_BATTERY_CHANGED));
    }

    public void stopBatteryMonitoring(Context context) {
        if (batteryReceiver != null) {
            context.unregisterReceiver(batteryReceiver);
            batteryReceiver = null;
        }
    }
}
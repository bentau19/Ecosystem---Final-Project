package com.example.android.data.datasource;

import android.content.Context;

import com.example.android.domain.entities.DeviceStorageStats;
import com.example.android.utils.DeviceUtils;
import com.example.android.utils.NetworkUtils;

/**
 * SystemDataSource acts as the primary access point for raw hardware and system data.
 * * Located in the Data Layer, this class encapsulates direct interactions with the
 * Android Framework and system utilities. Its main purpose is to shield the
 * rest of the application from Android-specific dependencies, ensuring that
 * repositories and use cases remain decoupled from the Context.
 * * Responsibilities include:
 * - Fetching network information (IP Address).
 * - Retrieving hardware identification (Device ID and Model).
 * - Monitoring device health (Battery percentage).
 * - Accessing raw storage metrics for further processing by the repository.
 * * By using the Application Context, this class ensures safe data retrieval
 * without risking memory leaks associated with Activity lifecycles.
 */
public class SystemDataSource {

    private final Context context;

    public SystemDataSource(Context context) {
        this.context = context.getApplicationContext();
    }

    public String getLocalIp() {
        return NetworkUtils.getLocalIpAddress(context);
    }

    public int getBattery() {
        return DeviceUtils.getBatteryPercentage(context);
    }

    public String getDeviceId() {
        return DeviceUtils.getDeviceId(context);
    }

    /**
     * Checks if the device is currently plugged into a power source.
     * Useful for the desktop dashboard to show charging status.
     */
    public boolean isDeviceCharging() {
        return DeviceUtils.isCharging(context);
    }

    public String getDeviceModel() {
        return DeviceUtils.getDeviceModel();
    }
    public DeviceStorageStats getRawStorageStats() {
        long total = DeviceUtils.getTotalStorage();
        long available = DeviceUtils.getAvailableStorage();
        return new DeviceStorageStats(total, available);
    }

}
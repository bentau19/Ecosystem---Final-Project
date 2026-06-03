package com.example.android.data.datasource;

import android.content.Context;

import com.example.android.domain.entities.DeviceStorageStats;
import com.example.android.utils.DeviceUtils;
import com.example.android.utils.NetworkUtils;

/**
 * SystemDataSource acts as the primary access point for raw hardware and system data.
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

    public boolean isDeviceCharging() {
        return DeviceUtils.isCharging(context);
    }

    public String getDeviceModel() {
        return DeviceUtils.getDeviceModel();
    }

    /**
     * Retrieves raw storage metrics.
     */
    public DeviceStorageStats getRawStorageStats() {
        long total = DeviceUtils.getTotalStorage();
        long available = DeviceUtils.getAvailableStorage();
        long used = total - available; 
        return new DeviceStorageStats(used, total);
    }
}

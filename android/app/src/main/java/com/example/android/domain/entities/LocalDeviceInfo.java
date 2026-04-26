package com.example.android.domain.entities;

/**
 * Entity representing the local Android device (this phone).
 * Contains hardware information and current system status.
 */
public class LocalDeviceInfo {
    private final String deviceId;
    private final String modelName;
    private String ipAddress;
    private int batteryLevel;
    private DeviceStorageStats storageStats;

    public LocalDeviceInfo(String deviceId, String modelName, String ipAddress) {
        this.deviceId = deviceId;
        this.modelName = modelName;
        this.ipAddress = ipAddress;
    }

    // Getters
    public String getDeviceId() { return deviceId; }
    public String getModelName() { return modelName; }
    public String getIpAddress() { return ipAddress; }
    public int getBatteryLevel() { return batteryLevel; }

    /**
     * @return DeviceStorageStats containing current used and total storage.
     */
    public DeviceStorageStats getStorageStats() { return storageStats; }

    // Setters
    public void setStorageStats(DeviceStorageStats stats) { this.storageStats = stats; }

    /**
     * Updates the current battery percentage.
     * @param batteryLevel Integer percentage (0-100).
     */
    public void setBatteryLevel(int batteryLevel) { this.batteryLevel = batteryLevel; }

    /**
     * Updates the current local IP address assigned to the device.
     * @param ipAddress String representing the IPv4 address.
     */
    public void setIpAddress(String ipAddress) { this.ipAddress = ipAddress; }
}
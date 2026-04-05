package com.example.android.data.models.entities;

public class LocalDeviceStats {
    private String phoneName;
    private String localIp;
    private int batteryLevel;
    private long totalStorageBytes;
    private long availableStorageBytes;

    public LocalDeviceStats(String phoneName, String localIp, int batteryLevel, long totalStorage, long availableStorage) {
        this.phoneName = phoneName;
        this.localIp = localIp;
        this.batteryLevel = batteryLevel;
        this.totalStorageBytes = totalStorage;
        this.availableStorageBytes = availableStorage;
    }

    // Getters
    public String getLocalIp() { return localIp; }
    public int getBatteryLevel() { return batteryLevel; }
    public String getPhoneName() { return phoneName; }
    public long getTotalStorageBytes() { return totalStorageBytes; }
    public long getAvailableStorageBytes() { return availableStorageBytes; }
}

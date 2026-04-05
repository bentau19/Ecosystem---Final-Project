package com.example.android.data.models.entities;

public class DeviceInfo {
    private LocalDeviceStats localStats;   // המידע של הטלפון
    private RemoteDeviceInfo remoteInfo;   // המידע של המחשב
    private boolean isConnected;
    private String connectionType;         // "WiFi" / "Bluetooth"

    public DeviceInfo(LocalDeviceStats local, RemoteDeviceInfo remote, boolean isConnected, String type) {
        this.localStats = local;
        this.remoteInfo = remote;
        this.isConnected = isConnected;
        this.connectionType = type;
    }

    // Getters נוחים לגישה ישירה מה-UI
    public LocalDeviceStats getLocalStats() { return localStats; }
    public RemoteDeviceInfo getRemoteInfo() { return remoteInfo; }
    public boolean isConnected() { return isConnected; }
    public String getConnectionType() { return connectionType; }

    // פונקציית עזר לחישוב אחוז אחסון (לשימוש ב-Progress Bar למשל)
    public int getStoragePercent() {
        if (localStats.getTotalStorageBytes() <= 0) return 0;
        long used = localStats.getTotalStorageBytes() - localStats.getAvailableStorageBytes();
        return (int) ((used * 100) / localStats.getTotalStorageBytes());
    }
}
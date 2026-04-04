package com.example.android.data.models;

public class DeviceInfo {
    private String phoneName;       // שם הפלאפון שלך
    private String pcName;          // שם המחשב המחובר
    private String remoteDeviceIp;       // כתובת ה-IP של המחשב המחובר
    private int batteryLevel;       // אחוז סוללה של הפלאפון (להצגה וסנכרון)
    private String connectionType;  // "WiFi" או "Bluetooth"
    private boolean isConnected;    // האם יש חיבור פעיל כרגע?

    public DeviceInfo(String phoneName, String pcName, String ipAddress,
                      int batteryLevel, String connectionType, boolean isConnected) {
        this.phoneName = phoneName;
        this.pcName = pcName;
        this.remoteDeviceIp = ipAddress;
        this.batteryLevel = batteryLevel;
        this.connectionType = connectionType;
        this.isConnected = isConnected;
    }

    // Getters - אלו הפונקציות שה-ViewModel ימשוך מהן מידע למסך
    public String getPhoneName() { return phoneName; }
    public String getPcName() { return pcName; }
    public String getIpAddress() { return remoteDeviceIp; }
    public int getBatteryLevel() { return batteryLevel; }
    public String getConnectionType() { return connectionType; }
    public boolean getIsConnected() { return isConnected; }
}
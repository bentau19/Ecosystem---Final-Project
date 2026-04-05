package com.example.android.data.models.entities;

public class RemoteDeviceInfo {
    private String pcName;
    private String pcIp;

    public RemoteDeviceInfo(String pcName, String pcIp) {
        this.pcName = pcName;
        this.pcIp = pcIp;
    }

    // Getters
    public String getPcName() { return pcName; }
    public String getPcIp() { return pcIp; }
}

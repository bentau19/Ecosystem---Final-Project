package com.example.android.data.models.entities;

public class DeviceConnectionState {
    private final LocalDeviceInfo localDevice;
    private RemoteDeviceInfo remotePC;

    public DeviceConnectionState(LocalDeviceInfo local) {
        this.localDevice = local;
    }

    /**
     * Source of truth for connection status:
     * If a remote PC object exists, the device is considered connected.
     */
    public boolean isConnected() {
        return remotePC != null;
    }

    // Getters & Setters
    public LocalDeviceInfo getLocalDevice() {
        return localDevice;
    }

    public RemoteDeviceInfo getRemotePC() {
        return remotePC;
    }

    public void setRemotePC(RemoteDeviceInfo remotePC) {
        this.remotePC = remotePC;
    }
}

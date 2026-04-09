package com.example.android.data.repositories;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.data.models.entities.DeviceInfo;
import com.example.android.data.models.entities.LocalDeviceStats;
import com.example.android.data.models.entities.RemoteDeviceInfo;
import com.example.android.data.models.enums.ConnectionType;

public class DeviceRepository {

    // one instance of the repository
    private static DeviceRepository instance;
    private final MutableLiveData<DeviceInfo> deviceInfo = new MutableLiveData<>();

    private DeviceRepository() {
        // נתוני דמה ראשוניים
        LocalDeviceStats initialLocal = new LocalDeviceStats("My Galaxy", "0.0.0.0", 0, 0, 0);
        RemoteDeviceInfo initialRemote = new RemoteDeviceInfo("None", "0.0.0.0");

        deviceInfo.setValue(new DeviceInfo(initialLocal, initialRemote, false, ConnectionType.NONE));
    }

    // get the one instance of the repository
    public static synchronized DeviceRepository getInstance() {
        if (instance == null) {
            instance = new DeviceRepository();
        }
        return instance;
    }

    public LiveData<DeviceInfo> getDeviceInfo() {
        return deviceInfo;
    }

    /**
     *update local stats
     */
    public void updateLocalStats(LocalDeviceStats newStats) {
        DeviceInfo current = deviceInfo.getValue();
        if (current != null) {
            deviceInfo.postValue(new DeviceInfo(
                    newStats,
                    current.getRemoteInfo(),
                    current.isConnected(),
                    current.getConnectionType()
            ));
        }
    }

    /**
     *update the local ip only
     */
    public void updateLocalIpOnly(String newIp) {
        DeviceInfo current = deviceInfo.getValue();
        if (current != null && current.getLocalStats() != null) {
            LocalDeviceStats oldStats = current.getLocalStats();
            LocalDeviceStats updatedStats = new LocalDeviceStats(
                    oldStats.getPhoneName(),
                    newIp,
                    oldStats.getBatteryLevel(),
                    oldStats.getTotalStorageBytes(),
                    oldStats.getAvailableStorageBytes()
            );
            updateLocalStats(updatedStats);
        }
    }

    public void updateFullInfo(LocalDeviceStats local, RemoteDeviceInfo remote, boolean isConnected) {
        deviceInfo.postValue(new DeviceInfo(
                local,
                remote,
                isConnected,
                isConnected ? ConnectionType.WIFI : ConnectionType.NONE
        ));
    }

    /**
     *update the remote info only
     */
    public void updateRemoteInfo(RemoteDeviceInfo newRemote, boolean isConnected) {
        DeviceInfo current = deviceInfo.getValue();
        if (current != null) {
            deviceInfo.postValue(new DeviceInfo(
                    current.getLocalStats(),
                    newRemote,
                    isConnected,
                    isConnected ? ConnectionType.WIFI : ConnectionType.NONE
            ));
        }
    }

    /**
     *change the connection status
     */
    public void setConnectionStatus(boolean connected) {
        DeviceInfo current = deviceInfo.getValue();
        if (current != null) {
            deviceInfo.postValue(new DeviceInfo(
                    current.getLocalStats(),
                    current.getRemoteInfo(),
                    connected,
                    connected ? current.getConnectionType() : ConnectionType.NONE
            ));
        }
    }
}
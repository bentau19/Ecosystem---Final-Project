package com.example.android.data.repositories;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.data.models.entities.DeviceInfo;
import com.example.android.data.models.entities.LocalDeviceStats;
import com.example.android.data.models.entities.RemoteDeviceInfo;

public class DeviceRepository {
    private final MutableLiveData<DeviceInfo> deviceInfo = new MutableLiveData<>();

    public DeviceRepository() {
        // נתוני דמה ראשוניים - הוספנו "0.0.0.0" ככתובת IP ראשונית ללוקאלי
        LocalDeviceStats initialLocal = new LocalDeviceStats("My Galaxy", "0.0.0.0", 0, 0, 0);
        RemoteDeviceInfo initialRemote = new RemoteDeviceInfo("None", "0.0.0.0");

        deviceInfo.setValue(new DeviceInfo(initialLocal, initialRemote, false, "None"));
    }

    public LiveData<DeviceInfo> getDeviceInfo() {
        return deviceInfo;
    }

    /**
     * עדכון נתוני הטלפון המקומיים (כולל ה-IP של הפלאפון, סוללה ואחסון)
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
     * פונקציית עזר לעדכון ה-IP של הפלאפון בלבד מבלי לדרוס את שאר הנתונים הלוקאליים
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
                isConnected ? "WiFi" : "None"
        ));
    }

    /**
     * עדכון נתוני המחשב המרוחק (מגיע מה-Serializer אחרי קבלת JSON)
     */
    public void updateRemoteInfo(RemoteDeviceInfo newRemote, boolean isConnected) {
        DeviceInfo current = deviceInfo.getValue();
        if (current != null) {
            deviceInfo.postValue(new DeviceInfo(
                    current.getLocalStats(),
                    newRemote,
                    isConnected,
                    isConnected ? "WiFi" : "None"
            ));
        }
    }

    /**
     * פונקציה לשינוי סטטוס חיבור בלבד
     */
    public void setConnectionStatus(boolean connected) {
        DeviceInfo current = deviceInfo.getValue();
        if (current != null) {
            deviceInfo.postValue(new DeviceInfo(
                    current.getLocalStats(),
                    current.getRemoteInfo(),
                    connected,
                    connected ? current.getConnectionType() : "None"
            ));
        }
    }
}
package com.example.android.data.repositories;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.data.models.DeviceInfo;

public class DeviceRepository {
    private final MutableLiveData<DeviceInfo> deviceInfo = new MutableLiveData<>();

    public DeviceRepository() {
        // נתוני דמה ראשוניים
        deviceInfo.setValue(new DeviceInfo("My Galaxy", "None", "0.0.0.0", 0, "None", false));
    }

    public LiveData<DeviceInfo> getDeviceInfo() {
        return deviceInfo;
    }

    // פונקציה מרכזית לעדכון ה-IP (בלי לבנות את כל האובייקט מחדש ב-VM)
    public void updateLocalIp(String ip) {
        DeviceInfo current = deviceInfo.getValue();
        if (current != null) {
            deviceInfo.postValue(new DeviceInfo(
                    current.getPhoneName(), current.getPcName(), ip,
                    current.getBatteryLevel(), current.getConnectionType(), current.getIsConnected()
            ));
        }
    }

    // פונקציית חיבור
    public void setConnection(String pcIp, int battery, boolean connected) {
        deviceInfo.postValue(new DeviceInfo(
                "My Galaxy", connected ? "My PC" : "None", pcIp,
                battery, connected ? "WiFi" : "None", connected
        ));
    }
}

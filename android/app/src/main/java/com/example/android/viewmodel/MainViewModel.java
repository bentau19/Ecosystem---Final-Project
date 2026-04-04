package com.example.android.viewmodel;

import android.content.Context;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.data.models.DeviceInfo;
import com.example.android.data.repositories.DeviceRepository;
import com.example.android.utils.NetworkUtils;

public class MainViewModel extends ViewModel {
    private final DeviceRepository repository = new DeviceRepository();

    // הפרגמנטים עדיין קוראים לזה כדי להציג מידע
    public LiveData<DeviceInfo> getDeviceInfo() {
        return repository.getDeviceInfo();
    }

    public void refreshIpAddress(Context context) {
        String ip = NetworkUtils.getLocalIpAddress(context);
        // ה-ViewModel רק אומר לריפוזיטורי: "תרענן את ה-IP"
        repository.updateLocalIp(ip);
    }

    public void connectToDevice(String pcIp, int batteryLevel) {
        // פקודה לריפוזיטורי לבצע חיבור
        repository.setConnection(pcIp, batteryLevel, true);
    }

    public void disconnectFromDevice() {
        // פקודה לריפוזיטורי לנתק
        repository.setConnection("0.0.0.0", 0, false);
    }
}
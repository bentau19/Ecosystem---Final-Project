package com.example.android.ui.viewmodel;

import android.content.Context;
import android.net.wifi.WifiManager;
import android.text.format.Formatter;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.models.DeviceInfo;

public class MainViewModel extends ViewModel {

    private final MutableLiveData<DeviceInfo> deviceInfo = new MutableLiveData<>();
    private final MutableLiveData<Integer> backupProgress = new MutableLiveData<>(0);
    private final MutableLiveData<String> antivirusStatus = new MutableLiveData<>("Ready to scan");

    public MainViewModel() {
        // נתוני דמה ראשוניים
        deviceInfo.setValue(new DeviceInfo(
                "My Galaxy",
                "None",
                "0.0.0.0",
                0,
                "None",
                false
        ));
    }

    // --- הפונקציה החדשה לשליפת ה-IP של הפלאפון ---
    public void refreshIpAddress(Context context) {
        try {
            // ניגשים למנהל ה-WiFi של המכשיר
            WifiManager wifiManager = (WifiManager) context.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            int ipInt = wifiManager.getConnectionInfo().getIpAddress();

            // המרה ממספר בינארי לפורמט נקודות (למשל 192.168.1.15)
            String currentIp = (ipInt == 0) ? "Disconnected" : Formatter.formatIpAddress(ipInt);

            // עדכון המודל הקיים מבלי לדרוס נתונים אחרים
            DeviceInfo current = deviceInfo.getValue();
            if (current != null) {
                updateDeviceInfo(new DeviceInfo(
                        current.getPhoneName(),
                        current.getPcName(),
                        currentIp,      // כאן נכנס ה-IP החדש של הפלאפון
                        current.getBatteryLevel(),
                        current.getConnectionType(),
                        current.getIsConnected()
                ));
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    // --- Getters ---
    public LiveData<DeviceInfo> getDeviceInfo() { return deviceInfo; }
    public LiveData<Integer> getBackupProgress() { return backupProgress; }
    public LiveData<String> getAntivirusStatus() { return antivirusStatus; }

    // --- Setters ---
    public void updateDeviceInfo(DeviceInfo info) {
        deviceInfo.postValue(info);
    }

    public void updateBackupProgress(int progress) {
        backupProgress.postValue(progress);
    }

    public void updateAntivirusStatus(String status) {
        antivirusStatus.postValue(status);
    }
}
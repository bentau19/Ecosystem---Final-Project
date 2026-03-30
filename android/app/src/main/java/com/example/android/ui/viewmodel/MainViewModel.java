package com.example.android.ui.viewmodel;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;
import androidx.lifecycle.ViewModel;

public class MainViewModel extends ViewModel {

    // --- מצב חיבור (Connection State) ---
    private final MutableLiveData<String> deviceName = new MutableLiveData<>("Disconnected");
    private final MutableLiveData<String> ipAddress = new MutableLiveData<>("0.0.0.0");
    private final MutableLiveData<Boolean> isConnected = new MutableLiveData<>(false);

    // --- נתוני מכשיר (Device Data) ---
    private final MutableLiveData<Integer> batteryLevel = new MutableLiveData<>(0);
    private final MutableLiveData<Boolean> isCharging = new MutableLiveData<>(false);

    // --- סטטוס פיצ'רים (Feature Progress) ---
    private final MutableLiveData<Integer> backupProgress = new MutableLiveData<>(0); // 0-100%
    private final MutableLiveData<String> antivirusStatus = new MutableLiveData<>("Ready to scan");

    // --- Getters (הפרגמנטים משתמשים באלו כדי להקשיב לשינויים) ---
    public LiveData<String> getDeviceName() { return deviceName; }
    public LiveData<String> getIpAddress() { return ipAddress; }
    public LiveData<Boolean> getIsConnected() { return isConnected; }
    public LiveData<Integer> getBatteryLevel() { return batteryLevel; }
    public LiveData<Integer> getBackupProgress() { return backupProgress; }

    // --- Setters (ה-Managers וה-Services משתמשים באלו כדי לעדכן נתונים) ---
    public void updateConnection(String name, String ip, boolean connected) {
        deviceName.postValue(name);
        ipAddress.postValue(ip);
        isConnected.postValue(connected);
    }

    public void updateBattery(int level, boolean charging) {
        batteryLevel.postValue(level);
        isCharging.postValue(charging);
    }

    public void updateBackupProgress(int progress) {
        backupProgress.postValue(progress);
    }
}
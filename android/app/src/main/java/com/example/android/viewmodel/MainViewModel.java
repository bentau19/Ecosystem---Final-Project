package com.example.android.viewmodel;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.domain.entities.DeviceConnectionState;
import com.example.android.domain.entities.DeviceStorageStats;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.repositories.DeviceRepository;
import com.example.android.domain.usecases.ConnectToDeviceUseCase;
import com.example.android.domain.usecases.ParseQrDataUseCase;
import com.example.android.domain.usecases.RefreshLocalStatsUseCase;

/**
 * ViewModel responsible for preparing and managing data for the UI.
 * It acts as a bridge between the DeviceRepository and the Fragments,
 * handling business logic such as QR data processing and status refreshing.
 */
public class MainViewModel extends ViewModel {
    private final RefreshLocalStatsUseCase refreshStats;
    private final ConnectToDeviceUseCase connectToDevice;
    private final ParseQrDataUseCase parseQr;

    private final DeviceRepository repository;
//    private android.content.BroadcastReceiver batteryReceiver;

    public MainViewModel(DeviceRepository repository,
                         RefreshLocalStatsUseCase refreshStats,
                         ConnectToDeviceUseCase connectToDevice,
                         ParseQrDataUseCase parseQr) {
        this.repository = repository;
        this.refreshStats = refreshStats;
        this.connectToDevice = connectToDevice;
        this.parseQr = parseQr;
    }

    /**
     * @return LiveData containing the unified connection state (Local device + Remote PC).
     */
    public LiveData<DeviceConnectionState> getConnectionState() {
        return repository.getConnectionState();
    }
    public LiveData<ConnectionStatus> getConnectionStatus() {
        return repository.getConnectionStatus();
    }

    /**
     * Refreshes local hardware statistics such as battery level and IP address.
     * Updates the repository which in turn notifies the UI observers.
     */
    public void refresh() {
        refreshStats.execute();
    }


    /**
     * Processes raw QR data and initiates the connection sequence.
     * @param qrData The raw string retrieved from the QR scanner.
     * @return true if the connection data was valid and initiated; false otherwise.
     */
    public boolean handleQr(String qrData) {
        RemoteDeviceInfo info = parseQr.execute(qrData);
        if (info == null) return false;
        connectToDevice.execute(info);
        return true;
    }

    /**
     * Commands the repository to terminate the current remote session.
     */
    public void disconnect() {
        connectToDevice.disconnect();
    }


    /**
     * Fetches the latest storage statistics from the repository.
     * @return DeviceStorageStats containing formatted status and usage percentage.
     */
    public DeviceStorageStats getStorageStats() {
        return repository.getLocalDeviceStorage();
    }
}
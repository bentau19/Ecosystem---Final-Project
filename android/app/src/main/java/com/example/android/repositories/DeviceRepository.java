package com.example.android.repositories;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.domain.entities.DeviceConnectionState;
import com.example.android.domain.entities.DeviceStorageStats;
import com.example.android.domain.entities.LocalDeviceInfo;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionType;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.utils.DeviceUtils;
import android.util.Log;

/**
 * Repository class that manages the device's connection state and hardware statistics.
 * Acts as the single source of truth for the UI regarding device status.
 *
 * Tracks:
 * - DeviceConnectionState: Local device info + Remote PC info
 * - ConnectionStatus: DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING, FAILED
 */
public class DeviceRepository {

    private static DeviceRepository instance;
    private static final String TAG = "DeviceRepository";

    // LiveData holds the unified connection state (local device + remote PC)
    private final MutableLiveData<DeviceConnectionState> connectionState = new MutableLiveData<>();

    // LiveData holds the connection status lifecycle (CONNECTING, CONNECTED, RECONNECTING, FAILED, etc.)
    private final MutableLiveData<ConnectionStatus> connectionStatus = new MutableLiveData<>(ConnectionStatus.DISCONNECTED);

    /**
     * @return The current connection state snapshot.
     */
    public DeviceConnectionState getCurrentConnectionState() {
        return connectionState.getValue();
    }

    /**
     * Manually triggers a LiveData update to notify all observers (UI) about internal state changes.
     * postValue is used to ensure thread safety when updating from background threads.
     */
    public void notifyStatusChanged() {
        DeviceConnectionState current = connectionState.getValue();
        if (current != null) {
            connectionState.postValue(current);
        }
    }

    private DeviceRepository(String deviceId, String modelName) {
        // Initialize local device data with REAL values
        LocalDeviceInfo initialLocal = new LocalDeviceInfo(
                deviceId,      // Real Device ID
                modelName,     // Real Model Name
                "0.0.0.0"      // Initial IP (will be updated later)
        );
        // Set initial state
        connectionState.setValue(new DeviceConnectionState(initialLocal));
    }

    /**
     * Singleton accessor with initialization data.
     */
    public static synchronized DeviceRepository getInstance(String deviceId, String model) {
        if (instance == null) {
            instance = new DeviceRepository(deviceId, model);
        }
        return instance;
    }

    /**
     * Singleton accessor for existing instance.
     * @throws IllegalStateException if repository hasn't been initialized yet.
     */
    public static DeviceRepository getInstance() {
        if (instance == null) {
            throw new IllegalStateException("Repository must be initialized with data first!");
        }
        return instance;
    }

    /**
     * @return LiveData containing the unified connection state.
     */
    public LiveData<DeviceConnectionState> getConnectionState() {
        return connectionState;
    }

    /**
     * Exposes the connection status (CONNECTING, CONNECTED, RECONNECTING, FAILED, etc.)
     * Useful for UI to show connection progress and errors.
     */
    public LiveData<ConnectionStatus> getConnectionStatus() {
        return connectionStatus;
    }

    /**
     * Gets the current connection status value synchronously.
     */
    public ConnectionStatus getCurrentConnectionStatus() {
        ConnectionStatus status = connectionStatus.getValue();
        return status != null ? status : ConnectionStatus.DISCONNECTED;
    }

    /**
     * Updates the connection status and notifies all observers.
     * This is called by the Transport/Service layer when connection state changes.
     */
    public void updateConnectionStatus(ConnectionStatus newStatus) {
        if (getCurrentConnectionStatus() != newStatus) {
            Log.d(TAG, "Connection status changed: " + newStatus.getDisplayName());
            connectionStatus.postValue(newStatus);
        }
    }

    /**
     * Establish session data for a remote computer.
     * @param pcName The name of the remote PC.
     * @param ip The target IP address.
     * @param type The connection protocol used.
     */
    public void connect(String pcName, String ip, ConnectionType type) {
        DeviceConnectionState current = connectionState.getValue();
        if (current != null) {
            // Create a new remote device object and inject it into the state
            RemoteDeviceInfo remote = new RemoteDeviceInfo(pcName, ip, type);
            current.setRemotePC(remote);

            // Notify all observers
            connectionState.postValue(current);
        }
    }

    /**
     * Terminates the current remote session and resets status.
     */
    public void disconnect() {
        DeviceConnectionState current = connectionState.getValue();
        if (current != null) {
            // Set remote PC to null - isConnected() will automatically return false
            current.setRemotePC(null);
            connectionState.postValue(current);
        }
        // Update status to disconnected
        updateConnectionStatus(ConnectionStatus.DISCONNECTED);
    }

    /**
     * Updates the local battery level in the current state.
     * @param newBatteryLevel Current battery percentage.
     */
    public void updateLocalBattery(int newBatteryLevel) {
        DeviceConnectionState current = connectionState.getValue();
        if (current != null && current.getLocalDevice() != null) {
            current.getLocalDevice().setBatteryLevel(newBatteryLevel);
            connectionState.postValue(current);
        }
    }

    /**
     * Batch update for local statistics.
     */
    public void refreshLocalStats(String ip, int battery) {
        updateLocalIp(ip);
        updateLocalBattery(battery);
    }


    /**
     * Updates the local IP address in the current state and notifies observers.
     * @param newIp The freshly fetched IP address from NetworkUtils.
     */
    public void updateLocalIp(String newIp) {
        DeviceConnectionState current = connectionState.getValue();
        if (current != null && current.getLocalDevice() != null) {
            current.getLocalDevice().setIpAddress(newIp);
            // Notify all observers about the change
            connectionState.postValue(current);
        }
    }

    /**
     * Fetches and calculates storage statistics with marketing rounding logic.
     * @return DeviceStorageStats object containing used and total GB.
     */
    public DeviceStorageStats getLocalDeviceStorage() {
        long totalBytes = DeviceUtils.getTotalStorage();
        long availableBytes = DeviceUtils.getAvailableStorage();

        // 1. Basic conversion to GB (as reported by the system)
        long realTotalGB = totalBytes / (1024 * 1024 * 1024);
        long availableGB = availableBytes / (1024 * 1024 * 1024);

        // 2. "Marketing Rounding" logic for standard capacities (64, 128, 256, 512)
        long marketingTotalGB;
        if (realTotalGB > 256) {
            marketingTotalGB = 512;
        } else if (realTotalGB > 128) {
            marketingTotalGB = 256;
        } else if (realTotalGB > 64) {
            marketingTotalGB = 128;
        } else {
            marketingTotalGB = 64;
        }

        // 3. Calculate "Used" based on Marketing Total for consistent UI ratio
        // (Marketing Total - Available = Logical Used space including system OS)
        long usedGB = marketingTotalGB - availableGB;

        return new DeviceStorageStats(usedGB, marketingTotalGB);
    }
}

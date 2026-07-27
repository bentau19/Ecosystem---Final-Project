package com.example.android.viewmodel;

import androidx.annotation.Nullable;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.domain.entities.DeviceConnectionState;
import com.example.android.domain.entities.DeviceStorageStats;
import com.example.android.domain.entities.DiscoveredPc;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.domain.enums.ConnectionType;
import com.example.android.domain.enums.DiscoveryStatus;
import com.example.android.repositories.BackupRepository;
import com.example.android.repositories.DeviceRepository;
import com.example.android.domain.usecases.ConnectToDeviceUseCase;
import com.example.android.domain.usecases.DisconnectDeviceUseCase;
import com.example.android.domain.usecases.PairWithPcUseCase;
import com.example.android.domain.usecases.RefreshLocalStatsUseCase;

/**
 * ViewModel responsible for preparing and managing data for the UI.
 * It acts as a bridge between the DeviceRepository and the Fragments.
 */
public class MainViewModel extends ViewModel {
    private final RefreshLocalStatsUseCase refreshStats;
    private final ConnectToDeviceUseCase connectToDevice;
    private final DisconnectDeviceUseCase disconnectDevice;
    private final PairWithPcUseCase pairWithPc;

    private final DeviceRepository repository;

    // Bluetooth discovery/pairing state, observed by ConnectFragment.
    private final MutableLiveData<DiscoveryStatus> discoveryStatus =
            new MutableLiveData<>(DiscoveryStatus.IDLE);
    private final MutableLiveData<DiscoveredPc> discoveredPc = new MutableLiveData<>();
    private final MutableLiveData<String> discoveryError = new MutableLiveData<>();
    private volatile String pairedMac;
    private boolean justDisconnected = false;
//    private android.content.BroadcastReceiver batteryReceiver;

    public MainViewModel(DeviceRepository repository,
                         RefreshLocalStatsUseCase refreshStats,
                         ConnectToDeviceUseCase connectToDevice,
                         DisconnectDeviceUseCase disconnectDevice,
                         PairWithPcUseCase pairWithPc) {
        this.repository = repository;
        this.refreshStats = refreshStats;
        this.connectToDevice = connectToDevice;
        this.disconnectDevice = disconnectDevice;
        this.pairWithPc = pairWithPc;
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


    // ── Bluetooth discovery & pairing ────────────────────────────────────────

    /** Discovery/pairing phase, observed by the UI to render progress and react to results. */
    public LiveData<DiscoveryStatus> getDiscoveryStatus() {
        return discoveryStatus;
    }

    /** The PC found over BLE — drives the "connect to this PC?" confirm dialog. */
    public LiveData<DiscoveredPc> getDiscoveredPc() {
        return discoveredPc;
    }

    /** Human-readable reason for the latest discovery/pairing failure. */
    public LiveData<String> getDiscoveryError() {
        return discoveryError;
    }

    /** The MAC bonded in the last successful pairing — used to start the hybrid connection. */
    @Nullable
    public String getPairedMac() {
        return pairedMac;
    }

    /** The remembered PC MAC from a previous pairing, or {@code null} on first run. */
    @Nullable
    public String getSavedAddress() {
        return pairWithPc.savedAddress();
    }

    /** The display name of the remembered PC, or {@code null} if not yet paired. */
    @Nullable
    public String getSavedDeviceName() {
        return pairWithPc.savedPcName();
    }

    /**
     * Starts scanning for the PC over BLE. On a known device the caller should connect directly
     * with {@link #getSavedAddress()} instead of scanning.
     */
    public void startDiscovery() {
        discoveryStatus.postValue(DiscoveryStatus.SCANNING);
        pairWithPc.discover(new PairWithPcUseCase.DiscoveryListener() {
            @Override
            public void onPcFound(DiscoveredPc pc) {
                discoveredPc.postValue(pc);
                discoveryStatus.postValue(DiscoveryStatus.PC_FOUND);
            }

            @Override
            public void onDiscoveryFailed(String reason) {
                discoveryError.postValue(reason);
                discoveryStatus.postValue(DiscoveryStatus.FAILED);
            }
        });
    }

    /** Bonds with the discovered PC after the user accepts the confirm dialog. */
    public void confirmPairing(String macAddress) {
        discoveryStatus.postValue(DiscoveryStatus.PAIRING);
        pairWithPc.pair(macAddress, new PairWithPcUseCase.PairingListener() {
            @Override
            public void onPaired(String mac) {
                pairedMac = mac;
                DiscoveredPc pc = discoveredPc.getValue();
                if (pc != null) pairWithPc.savePcName(pc.getName());
                discoveryStatus.postValue(DiscoveryStatus.PAIRED);
            }

            @Override
            public void onPairingFailed(String reason) {
                discoveryError.postValue(reason);
                discoveryStatus.postValue(DiscoveryStatus.FAILED);
            }
        });
    }

    /** Cancels an in-progress scan and returns to idle. */
    public void cancelDiscovery() {
        pairWithPc.stopDiscovery();
        discoveryStatus.postValue(DiscoveryStatus.IDLE);
    }

    /** Forgets the saved PC so the next attempt re-discovers (after a lost bond). */
    public void forgetSavedDevice() {
        pairWithPc.clearSaved();
    }

    /**
     * Records a hybrid (Bluetooth) connection to the bonded PC in the repository.
     * The real {@code connectHybrid} runs in {@code ConnectivityService};
     * this only updates the connection state so the UI reflects the attempt. The PC name is taken
     * from the discovered device when available and is later refined by the {@code pc_name} channel.
     */
    public void connectHybrid(String macAddress) {
        DiscoveredPc pc = discoveredPc.getValue();
        String pcName = (pc != null && macAddress.equals(pc.getMacAddress())) ? pc.getName() : "PC";
        RemoteDeviceInfo info =
                new RemoteDeviceInfo(pcName, null, macAddress, ConnectionType.BLUETOOTH);
        connectToDevice.execute(info);

        // Hand-off complete: reset the discovery phase so PAIRED is a one-shot. Otherwise the
        // status stays PAIRED and LiveData re-delivers it to a freshly created ConnectFragment
        // (e.g. after a disconnect navigates back here), which would re-trigger the connection —
        // an endless disconnect→reconnect loop.
        discoveryStatus.postValue(DiscoveryStatus.IDLE);
    }

    /**
     * Commands the repository to terminate the current remote session.
     */
    public void disconnect() {
        justDisconnected = true;
        disconnectDevice.execute();
    }

    public void setJustDisconnected() {
        justDisconnected = true;
    }

    /** Returns true once after a manual disconnect, then resets to false. */
    public boolean consumeJustDisconnected() {
        boolean v = justDisconnected;
        justDisconnected = false;
        return v;
    }

    /** Returns true once after a PC-initiated disconnect, then resets to false. */
    public boolean consumeJustDisconnectedByPc() {
        return repository.consumeJustDisconnectedByPc();
    }


    /**
     * Fetches the latest storage statistics from the repository.
     *
     * @return DeviceStorageStats containing formatted status and usage percentage.
     */
    public DeviceStorageStats getStorageStats() {
        return repository.getLocalDeviceStorage();
    }

    /**
     * Returns {@code true} when a backup scan or transfer is currently running or paused.
     *
     * <p>Delegates to {@link BackupRepository#isBackupActive()} so that
     * {@code ActionsFragment} can check backup state without holding a direct
     * reference to the repository layer.
     */
    public boolean isBackupActive() {
        return BackupRepository.getInstance().isBackupActive();
    }
}
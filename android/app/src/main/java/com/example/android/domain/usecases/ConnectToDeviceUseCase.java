package com.example.android.domain.usecases;

import com.example.android.repositories.DeviceRepository;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionType;

public class ConnectToDeviceUseCase {

    private final DeviceRepository repository;

    public ConnectToDeviceUseCase(DeviceRepository repository) {
        this.repository = repository;
    }

    /**
     * Records the chosen remote PC in the repository, routing by connection type: the hybrid
     * (Bluetooth) path uses the MAC, the Wi-Fi path uses the IP. One entry point, one branch —
     * the existing Wi-Fi behaviour is unchanged.
     */
    public void execute(RemoteDeviceInfo info) {
        if (info.getConnectionType() == ConnectionType.BLUETOOTH) {
            repository.connectHybrid(info.getPcName(), info.getMacAddress());
        } else {
            repository.connect(info.getPcName(), info.getPcIp(), info.getConnectionType());
        }
    }
}

package com.example.android.domain.usecases;

import com.example.android.repositories.DeviceRepository;
import com.example.android.domain.entities.RemoteDeviceInfo;

public class ConnectToDeviceUseCase {

    private final DeviceRepository repository;

    public ConnectToDeviceUseCase(DeviceRepository repository) {
        this.repository = repository;
    }

    public void execute(RemoteDeviceInfo info) {
        repository.connect(info.getPcName(), info.getPcIp(), info.getConnectionType());
    }
}

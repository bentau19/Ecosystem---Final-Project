package com.example.android.domain.usecases;

import com.example.android.data.datasource.SystemDataSource;
import com.example.android.data.repositories.DeviceRepository;

public class RefreshLocalStatsUseCase {

    private final DeviceRepository repository;
    private final SystemDataSource system;

    public RefreshLocalStatsUseCase(DeviceRepository repository, SystemDataSource system) {
        this.repository = repository;
        this.system = system;
    }

    public void execute() {
        String ip = system.getLocalIp();
        int battery = system.getBattery();
        repository.refreshLocalStats(ip, battery);
    }
}



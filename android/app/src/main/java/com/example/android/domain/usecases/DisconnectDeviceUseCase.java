package com.example.android.domain.usecases;

import com.example.android.repositories.DeviceRepository;

/**
 * UseCase responsible for terminating the current remote session.
 *
 * <p>Clears the RemoteDeviceInfo from the repository, which automatically
 * propagates a DISCONNECTED state to all LiveData observers (UI). Any
 * additional disconnect logic (analytics, transfer guards, etc.) belongs here
 * — not in the Activity or Service.
 */
public class DisconnectDeviceUseCase {

    private final DeviceRepository repository;

    /**
     * @param repository The application's single source of truth for connection state.
     */
    public DisconnectDeviceUseCase(DeviceRepository repository) {
        this.repository = repository;
    }

    /**
     * Clears the remote PC from the connection state and resets status to DISCONNECTED.
     * Safe to call multiple times (idempotent).
     */
    public void execute() {
        repository.disconnect();
    }
}

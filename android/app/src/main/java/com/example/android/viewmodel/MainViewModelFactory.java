package com.example.android.viewmodel;

import android.app.Application;

import androidx.annotation.NonNull;
import androidx.lifecycle.ViewModel;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.data.datasource.SystemDataSource;
import com.example.android.repositories.DeviceRepository;
import com.example.android.domain.usecases.ConnectToDeviceUseCase;
import com.example.android.domain.usecases.ParseQrDataUseCase;
import com.example.android.domain.usecases.RefreshLocalStatsUseCase;

/**
 * Factory class responsible for instantiating the MainViewModel with all required dependencies.
 * It handles the creation of DataSources, Repositories, and UseCases.
 */
public class MainViewModelFactory implements ViewModelProvider.Factory {

    private final Application application;

    public MainViewModelFactory(Application application) {
        this.application = application;
    }

    @NonNull
    @Override
    @SuppressWarnings("unchecked")
    public <T extends ViewModel> T create(@NonNull Class<T> modelClass) {

        if (modelClass.isAssignableFrom(MainViewModel.class)) {

            // 1. Initialize DataSource - The only component that interacts with the Android Context
            SystemDataSource systemDataSource =
                    new SystemDataSource(application.getApplicationContext());

            // 2. Initialize Repository
            DeviceRepository repository =
                    DeviceRepository.getInstance(
                            systemDataSource.getDeviceId(),
                            systemDataSource.getDeviceModel()
                    );

            // 3. Initialize UseCases - Injected with their respective dependencies
            RefreshLocalStatsUseCase refreshStats =
                    new RefreshLocalStatsUseCase(repository, systemDataSource);

            ConnectToDeviceUseCase connectToDevice =
                    new ConnectToDeviceUseCase(repository);

            ParseQrDataUseCase parseQr =
                    new ParseQrDataUseCase();

            // 4. Create the ViewModel with the fully prepared dependency graph
            return (T) new MainViewModel(
                    repository,
                    refreshStats,
                    connectToDevice,
                    parseQr
            );
        }

        throw new IllegalArgumentException("Unknown ViewModel class");
    }
}
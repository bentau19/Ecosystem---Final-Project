package com.example.android.viewmodel;

import android.app.Application;

import androidx.annotation.NonNull;
import androidx.lifecycle.ViewModel;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.data.datasource.BackupDataSource;
import com.example.android.domain.usecases.ScanBackupFilesUseCase;
import com.example.android.repositories.BackupRepository;

/**
 * Manual DI factory for {@link BackupViewModel}.
 *
 * <p>Constructs the dependency graph:
 * <pre>
 *   Application (Context)
 *     └─► BackupDataSource
 *           └─► ScanBackupFilesUseCase
 *                 └─► BackupViewModel ◄── BackupRepository (singleton)
 * </pre>
 *
 * <p>Usage in a Fragment:
 * <pre>{@code
 *   backupViewModel = new ViewModelProvider(
 *           this, new BackupViewModelFactory(requireActivity().getApplication()))
 *       .get(BackupViewModel.class);
 * }</pre>
 */
public class BackupViewModelFactory implements ViewModelProvider.Factory {

    private final Application application;

    public BackupViewModelFactory(Application application) {
        this.application = application;
    }

    @NonNull
    @Override
    @SuppressWarnings("unchecked")
    public <T extends ViewModel> T create(@NonNull Class<T> modelClass) {
        if (modelClass.isAssignableFrom(BackupViewModel.class)) {

            // 1. DataSource — handles all Android I/O (stateless, safe to share)
            BackupDataSource dataSource = new BackupDataSource();

            // 2. UseCase — injects ApplicationContext to prevent Activity leaks
            ScanBackupFilesUseCase scanUseCase =
                    new ScanBackupFilesUseCase(dataSource, application.getApplicationContext());

            // 3. Repository singleton
            BackupRepository repository = BackupRepository.getInstance();

            return (T) new BackupViewModel(repository, scanUseCase);
        }

        throw new IllegalArgumentException("Unknown ViewModel class: " + modelClass.getName());
    }
}

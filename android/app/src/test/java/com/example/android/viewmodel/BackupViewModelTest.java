package com.example.android.viewmodel;

import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertSame;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;
import androidx.lifecycle.MutableLiveData;

import com.example.android.domain.entities.BackupOptions;
import com.example.android.domain.enums.BackupScanStatus;
import com.example.android.domain.enums.BackupTransferStatus;
import com.example.android.domain.usecases.ScanBackupFilesUseCase;
import com.example.android.repositories.BackupRepository;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.mockito.Mock;
import org.mockito.junit.MockitoJUnitRunner;

/**
 * Unit tests for BackupViewModel.
 *
 * BackupViewModel is a thin delegation layer: it forwards user actions to
 * BackupRepository and exposes its LiveData to the Fragment. These tests verify
 * that delegation and LiveData forwarding are correct.
 *
 * BackupRepository is mocked (Mockito can mock concrete classes) so no singleton
 * reset is needed here — the ViewModel receives the repository via constructor injection.
 */
@RunWith(MockitoJUnitRunner.class)
public class BackupViewModelTest {

    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    @Mock
    private BackupRepository mockRepository;

    @Mock
    private ScanBackupFilesUseCase mockScanUseCase;

    private BackupViewModel viewModel;

    @Before
    public void setUp() {
        // Stub LiveData accessors — the ViewModel reads these in its getters
        when(mockRepository.getScanStatus())
                .thenReturn(new MutableLiveData<>(BackupScanStatus.IDLE));
        when(mockRepository.getTransferStatus())
                .thenReturn(new MutableLiveData<>(BackupTransferStatus.IDLE));
        when(mockRepository.getTransferSent())
                .thenReturn(new MutableLiveData<>(0));
        when(mockRepository.getTransferTotal())
                .thenReturn(new MutableLiveData<>(0));
        when(mockRepository.getFailedCount())
                .thenReturn(new MutableLiveData<>(0));

        viewModel = new BackupViewModel(mockRepository, mockScanUseCase);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // startScan — delegation to repository.requestScan
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void startScan_delegatesAllMediaModeToRepository() {
        BackupOptions options = new BackupOptions(true, 2, false);

        viewModel.startScan("all_media", null, options);

        verify(mockRepository).requestScan("all_media", null, options);
    }

    @Test
    public void startScan_delegatesFolderModeToRepository() {
        // null uri simulates a folder URI in unit-test scope (android.net.Uri is an Android type)
        BackupOptions options = new BackupOptions(false, 1, true);

        viewModel.startScan("folder", null, options);

        verify(mockRepository).requestScan("folder", null, options);
    }

    @Test
    public void startScan_withNullOptions_stillDelegatesToRepository() {
        // The repository handles null options by substituting a default — the
        // ViewModel must pass it through unchanged.
        viewModel.startScan("all_media", null, null);

        verify(mockRepository).requestScan("all_media", null, null);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // LiveData forwarding
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void getScanStatus_returnsRepositoryLiveData() {
        assertNotNull(viewModel.getScanStatus());
        assertSame(mockRepository.getScanStatus(), viewModel.getScanStatus());
    }

    @Test
    public void getTransferStatus_returnsRepositoryLiveData() {
        assertNotNull(viewModel.getTransferStatus());
        assertSame(mockRepository.getTransferStatus(), viewModel.getTransferStatus());
    }

    @Test
    public void getTransferSent_returnsRepositoryLiveData() {
        assertNotNull(viewModel.getTransferSent());
        assertSame(mockRepository.getTransferSent(), viewModel.getTransferSent());
    }

    @Test
    public void getTransferTotal_returnsRepositoryLiveData() {
        assertNotNull(viewModel.getTransferTotal());
        assertSame(mockRepository.getTransferTotal(), viewModel.getTransferTotal());
    }

    @Test
    public void getFailedCount_returnsRepositoryLiveData() {
        assertNotNull(viewModel.getFailedCount());
        assertSame(mockRepository.getFailedCount(), viewModel.getFailedCount());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Constructor side-effect — ScanActionListener registration
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void constructor_registersItselfAsScanActionListener() {
        // Verify that the ViewModel registered a non-null listener on construction
        // so BackupRepository.requestScan() has someone to notify.
        verify(mockRepository).setActionListener(
                org.mockito.ArgumentMatchers.notNull()
        );
    }
}

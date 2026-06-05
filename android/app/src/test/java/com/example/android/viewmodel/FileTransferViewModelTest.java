package com.example.android.viewmodel;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;

import com.example.android.domain.entities.FileTransferRequest;
import com.example.android.domain.enums.FileTransferStatus;
import com.example.android.repositories.FileTransferRepository;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;

import java.lang.reflect.Field;

/**
 * Unit tests for FileTransferViewModel.
 *
 * Because FileTransferViewModel delegates all logic to FileTransferRepository.getInstance(),
 * these tests work with the real repository singleton — verifying that ViewModel actions
 * produce the expected LiveData state visible to the UI.
 *
 * The singleton is reset via reflection before each test (same pattern as DeviceRepositoryTest)
 * to guarantee full test isolation.
 */
public class FileTransferViewModelTest {

    // Forces LiveData.postValue() to execute synchronously so we can assert immediately
    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    private FileTransferViewModel viewModel;
    private FileTransferRepository repository;

    @Before
    public void setUp() throws Exception {
        // Reset the singleton so every test starts from IDLE with no listeners
        Field instanceField = FileTransferRepository.class.getDeclaredField("instance");
        instanceField.setAccessible(true);
        instanceField.set(null, null);

        // Both viewModel and repository now point to the same fresh singleton
        repository = FileTransferRepository.getInstance();
        viewModel = new FileTransferViewModel();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Initial state
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void initialState_transferStatusIsIdle() {
        assertEquals(FileTransferStatus.IDLE, viewModel.getTransferStatus().getValue());
    }

    @Test
    public void initialState_pendingRequestIsNull() {
        assertNull(viewModel.getPendingRequest().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // acceptTransfer
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void acceptTransfer_statusBecomesReceiving() {
        // Arrange: a pending request must exist for accept to fire the listener
        repository.onTransferRequested(new FileTransferRequest("photo.jpg", 1_024L));

        viewModel.acceptTransfer();

        assertEquals(FileTransferStatus.RECEIVING, viewModel.getTransferStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // rejectTransfer
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void rejectTransfer_statusBecomesRejected() {
        repository.onTransferRequested(new FileTransferRequest("photo.jpg", 1_024L));

        viewModel.rejectTransfer();

        assertEquals(FileTransferStatus.REJECTED, viewModel.getTransferStatus().getValue());
    }

    @Test
    public void rejectTransfer_clearsPendingRequest() {
        repository.onTransferRequested(new FileTransferRequest("photo.jpg", 1_024L));

        viewModel.rejectTransfer();

        assertNull(viewModel.getPendingRequest().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // reset
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void reset_afterCompletion_statusBecomesIdle() {
        repository.onTransferRequested(new FileTransferRequest("video.mp4", 10_000_000L));
        repository.onTransferCompleted();

        viewModel.reset();

        assertEquals(FileTransferStatus.IDLE, viewModel.getTransferStatus().getValue());
    }

    @Test
    public void reset_afterRejection_statusBecomesIdle() {
        repository.onTransferRequested(new FileTransferRequest("video.mp4", 10_000_000L));
        repository.onTransferRejected();

        viewModel.reset();

        assertEquals(FileTransferStatus.IDLE, viewModel.getTransferStatus().getValue());
    }

    @Test
    public void reset_afterFailure_statusBecomesIdle() {
        repository.onTransferRequested(new FileTransferRequest("video.mp4", 10_000_000L));
        repository.onTransferFailed();

        viewModel.reset();

        assertEquals(FileTransferStatus.IDLE, viewModel.getTransferStatus().getValue());
    }

    @Test
    public void reset_clearsPendingRequest() {
        repository.onTransferRequested(new FileTransferRequest("doc.pdf", 500L));
        repository.onTransferFailed();

        viewModel.reset();

        assertNull(viewModel.getPendingRequest().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // LiveData exposure — ViewModel is a transparent window onto the repository
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void getPendingRequest_reflectsIncomingRequest() {
        FileTransferRequest request = new FileTransferRequest("archive.zip", 2_048_000L);

        repository.onTransferRequested(request);

        FileTransferRequest exposed = viewModel.getPendingRequest().getValue();
        assertNotNull(exposed);
        assertEquals("archive.zip", exposed.getFileName());
        assertEquals(2_048_000L, exposed.getFileSizeBytes());
    }

    @Test
    public void getTransferStatus_reflectsFullLifecycle() {
        // Walk the happy path entirely through the ViewModel's LiveData
        assertEquals(FileTransferStatus.IDLE, viewModel.getTransferStatus().getValue());

        repository.onTransferRequested(new FileTransferRequest("backup.zip", 1_000L));
        assertEquals(FileTransferStatus.PENDING_APPROVAL, viewModel.getTransferStatus().getValue());

        viewModel.acceptTransfer();
        assertEquals(FileTransferStatus.RECEIVING, viewModel.getTransferStatus().getValue());

        repository.onTransferCompleted();
        assertEquals(FileTransferStatus.COMPLETED, viewModel.getTransferStatus().getValue());

        viewModel.reset();
        assertEquals(FileTransferStatus.IDLE, viewModel.getTransferStatus().getValue());
    }
}

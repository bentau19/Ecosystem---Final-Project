package com.example.android.viewmodel;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;

import com.example.android.domain.entities.ReceiveFileRequest;
import com.example.android.domain.enums.ReceiveFileStatus;
import com.example.android.repositories.ReceiveFileRepository;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;

import java.lang.reflect.Field;

/**
 * Unit tests for FileTransferViewModel.
 *
 * Because FileTransferViewModel delegates all logic to ReceiveFileRepository.getInstance(),
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
    private ReceiveFileRepository repository;

    @Before
    public void setUp() throws Exception {
        // Reset the singleton so every test starts from IDLE with no listeners
        Field instanceField = ReceiveFileRepository.class.getDeclaredField("instance");
        instanceField.setAccessible(true);
        instanceField.set(null, null);

        // Both viewModel and repository now point to the same fresh singleton
        repository = ReceiveFileRepository.getInstance();
        viewModel = new FileTransferViewModel();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Initial state
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void initialState_transferStatusIsIdle() {
        assertEquals(ReceiveFileStatus.IDLE, viewModel.getTransferStatus().getValue());
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
        repository.onTransferRequested(new ReceiveFileRequest("photo.jpg", 1_024L));

        viewModel.acceptTransfer();

        assertEquals(ReceiveFileStatus.RECEIVING, viewModel.getTransferStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // rejectTransfer
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void rejectTransfer_statusBecomesRejected() {
        repository.onTransferRequested(new ReceiveFileRequest("photo.jpg", 1_024L));

        viewModel.rejectTransfer();

        assertEquals(ReceiveFileStatus.REJECTED, viewModel.getTransferStatus().getValue());
    }

    @Test
    public void rejectTransfer_clearsPendingRequest() {
        repository.onTransferRequested(new ReceiveFileRequest("photo.jpg", 1_024L));

        viewModel.rejectTransfer();

        assertNull(viewModel.getPendingRequest().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // reset
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void reset_afterCompletion_statusBecomesIdle() {
        repository.onTransferRequested(new ReceiveFileRequest("video.mp4", 10_000_000L));
        repository.onTransferCompleted();

        viewModel.reset();

        assertEquals(ReceiveFileStatus.IDLE, viewModel.getTransferStatus().getValue());
    }

    @Test
    public void reset_afterRejection_statusBecomesIdle() {
        repository.onTransferRequested(new ReceiveFileRequest("video.mp4", 10_000_000L));
        repository.onTransferRejected();

        viewModel.reset();

        assertEquals(ReceiveFileStatus.IDLE, viewModel.getTransferStatus().getValue());
    }

    @Test
    public void reset_afterFailure_statusBecomesIdle() {
        repository.onTransferRequested(new ReceiveFileRequest("video.mp4", 10_000_000L));
        repository.onTransferFailed();

        viewModel.reset();

        assertEquals(ReceiveFileStatus.IDLE, viewModel.getTransferStatus().getValue());
    }

    @Test
    public void reset_clearsPendingRequest() {
        repository.onTransferRequested(new ReceiveFileRequest("doc.pdf", 500L));
        repository.onTransferFailed();

        viewModel.reset();

        assertNull(viewModel.getPendingRequest().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // LiveData exposure — ViewModel is a transparent window onto the repository
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void getPendingRequest_reflectsIncomingRequest() {
        ReceiveFileRequest request = new ReceiveFileRequest("archive.zip", 2_048_000L);

        repository.onTransferRequested(request);

        ReceiveFileRequest exposed = viewModel.getPendingRequest().getValue();
        assertNotNull(exposed);
        assertEquals("archive.zip", exposed.getFileName());
        assertEquals(2_048_000L, exposed.getFileSizeBytes());
    }

    @Test
    public void getTransferStatus_reflectsFullLifecycle() {
        // Walk the happy path entirely through the ViewModel's LiveData
        assertEquals(ReceiveFileStatus.IDLE, viewModel.getTransferStatus().getValue());

        repository.onTransferRequested(new ReceiveFileRequest("backup.zip", 1_000L));
        assertEquals(ReceiveFileStatus.PENDING_APPROVAL, viewModel.getTransferStatus().getValue());

        viewModel.acceptTransfer();
        assertEquals(ReceiveFileStatus.RECEIVING, viewModel.getTransferStatus().getValue());

        repository.onTransferCompleted();
        assertEquals(ReceiveFileStatus.COMPLETED, viewModel.getTransferStatus().getValue());

        viewModel.reset();
        assertEquals(ReceiveFileStatus.IDLE, viewModel.getTransferStatus().getValue());
    }
}

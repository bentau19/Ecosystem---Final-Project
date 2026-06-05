package com.example.android.repositories;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;

import com.example.android.domain.entities.ReceiveFileRequest;
import com.example.android.domain.enums.ReceiveFileStatus;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.mockito.Mock;
import org.mockito.junit.MockitoJUnitRunner;

import java.lang.reflect.Field;

/**
 * Unit tests for ReceiveFileRepository — verifies all state-machine transitions
 * and listener callbacks using the same reflection-based singleton reset pattern
 * used in DeviceRepositoryTest.
 */
@RunWith(MockitoJUnitRunner.class)
public class ReceiveFileRepositoryTest {

    // Forces LiveData.postValue() to execute synchronously so we can assert immediately
    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    @Mock
    private ReceiveFileRepository.ReceiveFileActionListener mockActionListener;

    @Mock
    private ReceiveFileRepository.IncomingRequestListener mockIncomingRequestListener;

    private ReceiveFileRepository repository;

    @Before
    public void setUp() throws Exception {
        // Reset the singleton so every test starts from a clean IDLE state
        Field instanceField = ReceiveFileRepository.class.getDeclaredField("instance");
        instanceField.setAccessible(true);
        instanceField.set(null, null);

        repository = ReceiveFileRepository.getInstance();
        repository.setActionListener(mockActionListener);
        repository.setIncomingRequestListener(mockIncomingRequestListener);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Initial state
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void initialState_isIdleWithNullRequest() {
        assertEquals(ReceiveFileStatus.IDLE, repository.getTransferStatus().getValue());
        assertNull(repository.getPendingRequest().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onTransferRequested  (IDLE → PENDING_APPROVAL)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onTransferRequested_setsPendingApprovalStatus() {
        repository.onTransferRequested(new ReceiveFileRequest("photo.jpg", 4_194_304L));

        assertEquals(ReceiveFileStatus.PENDING_APPROVAL, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferRequested_storesFileNameAndSize() {
        ReceiveFileRequest request = new ReceiveFileRequest("document.pdf", 1_048_576L);

        repository.onTransferRequested(request);

        ReceiveFileRequest stored = repository.getPendingRequest().getValue();
        assertNotNull(stored);
        assertEquals("document.pdf", stored.getFileName());
        assertEquals(1_048_576L, stored.getFileSizeBytes());
    }

    @Test
    public void onTransferRequested_notifiesIncomingRequestListener() {
        ReceiveFileRequest request = new ReceiveFileRequest("video.mp4", 102_400_000L);

        repository.onTransferRequested(request);

        verify(mockIncomingRequestListener).onRequestArrived(request);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onTransferAccepted  (PENDING_APPROVAL → RECEIVING)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onTransferAccepted_setsReceivingStatus() {
        repository.onTransferRequested(new ReceiveFileRequest("video.mp4", 102_400L));

        repository.onTransferAccepted();

        assertEquals(ReceiveFileStatus.RECEIVING, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferAccepted_callsListenerWithCorrectFileName() {
        repository.onTransferRequested(new ReceiveFileRequest("video.mp4", 102_400L));

        repository.onTransferAccepted();

        verify(mockActionListener).onUserAccepted("video.mp4");
    }

    @Test
    public void onTransferAccepted_doesNotCallOnUserRejected() {
        repository.onTransferRequested(new ReceiveFileRequest("video.mp4", 102_400L));

        repository.onTransferAccepted();

        verify(mockActionListener, never()).onUserRejected();
    }

    @Test
    public void onTransferAccepted_withNoListener_doesNotCrash() {
        // Arrange: no listener registered
        repository.setActionListener(null);
        repository.onTransferRequested(new ReceiveFileRequest("file.zip", 512L));

        // Should not throw NullPointerException
        repository.onTransferAccepted();

        assertEquals(ReceiveFileStatus.RECEIVING, repository.getTransferStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onTransferRejected  (PENDING_APPROVAL → REJECTED)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onTransferRejected_setsRejectedStatus() {
        repository.onTransferRequested(new ReceiveFileRequest("image.png", 2048L));

        repository.onTransferRejected();

        assertEquals(ReceiveFileStatus.REJECTED, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferRejected_clearsPendingRequest() {
        repository.onTransferRequested(new ReceiveFileRequest("image.png", 2048L));

        repository.onTransferRejected();

        assertNull(repository.getPendingRequest().getValue());
    }

    @Test
    public void onTransferRejected_callsListenerOnUserRejected() {
        repository.onTransferRequested(new ReceiveFileRequest("image.png", 2048L));

        repository.onTransferRejected();

        verify(mockActionListener).onUserRejected();
    }

    @Test
    public void onTransferRejected_doesNotCallOnUserAccepted() {
        repository.onTransferRequested(new ReceiveFileRequest("image.png", 2048L));

        repository.onTransferRejected();

        verify(mockActionListener, never()).onUserAccepted(anyString());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onTransferCompleted  (RECEIVING → COMPLETED)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onTransferCompleted_setsCompletedStatus() {
        repository.onTransferRequested(new ReceiveFileRequest("archive.zip", 8_192_000L));
        repository.onTransferAccepted();

        repository.onTransferCompleted();

        assertEquals(ReceiveFileStatus.COMPLETED, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferCompleted_clearsPendingRequest() {
        repository.onTransferRequested(new ReceiveFileRequest("archive.zip", 8_192_000L));
        repository.onTransferAccepted();

        repository.onTransferCompleted();

        assertNull(repository.getPendingRequest().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onTransferFailed  (any state → FAILED)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onTransferFailed_setsFailedStatus() {
        repository.onTransferRequested(new ReceiveFileRequest("data.bin", 65_536L));

        repository.onTransferFailed();

        assertEquals(ReceiveFileStatus.FAILED, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferFailed_clearsPendingRequest() {
        repository.onTransferRequested(new ReceiveFileRequest("data.bin", 65_536L));

        repository.onTransferFailed();

        assertNull(repository.getPendingRequest().getValue());
    }

    @Test
    public void onTransferFailed_fromReceivingState_setsFailedStatus() {
        // Failure can happen mid-transfer, not just at PENDING_APPROVAL
        repository.onTransferRequested(new ReceiveFileRequest("movie.mkv", 1_000_000_000L));
        repository.onTransferAccepted();

        repository.onTransferFailed();

        assertEquals(ReceiveFileStatus.FAILED, repository.getTransferStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // reset  (terminal state → IDLE)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void reset_afterCompleted_returnsToIdle() {
        repository.onTransferRequested(new ReceiveFileRequest("song.mp3", 5_000_000L));
        repository.onTransferAccepted();
        repository.onTransferCompleted();

        repository.reset();

        assertEquals(ReceiveFileStatus.IDLE, repository.getTransferStatus().getValue());
        assertNull(repository.getPendingRequest().getValue());
    }

    @Test
    public void reset_afterRejected_returnsToIdle() {
        repository.onTransferRequested(new ReceiveFileRequest("song.mp3", 5_000_000L));
        repository.onTransferRejected();

        repository.reset();

        assertEquals(ReceiveFileStatus.IDLE, repository.getTransferStatus().getValue());
    }

    @Test
    public void reset_afterFailed_returnsToIdle() {
        repository.onTransferRequested(new ReceiveFileRequest("song.mp3", 5_000_000L));
        repository.onTransferFailed();

        repository.reset();

        assertEquals(ReceiveFileStatus.IDLE, repository.getTransferStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Full lifecycle smoke test
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void fullHappyPath_idleThroughCompletedAndBackToIdle() {
        // IDLE
        assertEquals(ReceiveFileStatus.IDLE, repository.getTransferStatus().getValue());

        // PC sends metadata → PENDING_APPROVAL
        repository.onTransferRequested(new ReceiveFileRequest("backup.zip", 2_048_000L));
        assertEquals(ReceiveFileStatus.PENDING_APPROVAL, repository.getTransferStatus().getValue());

        // User accepts → RECEIVING
        repository.onTransferAccepted();
        assertEquals(ReceiveFileStatus.RECEIVING, repository.getTransferStatus().getValue());

        // All bytes saved → COMPLETED
        repository.onTransferCompleted();
        assertEquals(ReceiveFileStatus.COMPLETED, repository.getTransferStatus().getValue());

        // UI acknowledges → IDLE
        repository.reset();
        assertEquals(ReceiveFileStatus.IDLE, repository.getTransferStatus().getValue());
    }
}

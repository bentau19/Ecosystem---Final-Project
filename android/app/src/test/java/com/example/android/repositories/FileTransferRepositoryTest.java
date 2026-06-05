package com.example.android.repositories;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;

import com.example.android.domain.entities.FileTransferRequest;
import com.example.android.domain.enums.FileTransferStatus;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.mockito.Mock;
import org.mockito.junit.MockitoJUnitRunner;

import java.lang.reflect.Field;

/**
 * Unit tests for FileTransferRepository — verifies all state-machine transitions
 * and listener callbacks using the same reflection-based singleton reset pattern
 * used in DeviceRepositoryTest.
 */
@RunWith(MockitoJUnitRunner.class)
public class FileTransferRepositoryTest {

    // Forces LiveData.postValue() to execute synchronously so we can assert immediately
    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    @Mock
    private FileTransferRepository.FileTransferActionListener mockActionListener;

    @Mock
    private FileTransferRepository.IncomingRequestListener mockIncomingRequestListener;

    private FileTransferRepository repository;

    @Before
    public void setUp() throws Exception {
        // Reset the singleton so every test starts from a clean IDLE state
        Field instanceField = FileTransferRepository.class.getDeclaredField("instance");
        instanceField.setAccessible(true);
        instanceField.set(null, null);

        repository = FileTransferRepository.getInstance();
        repository.setActionListener(mockActionListener);
        repository.setIncomingRequestListener(mockIncomingRequestListener);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Initial state
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void initialState_isIdleWithNullRequest() {
        assertEquals(FileTransferStatus.IDLE, repository.getTransferStatus().getValue());
        assertNull(repository.getPendingRequest().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onTransferRequested  (IDLE → PENDING_APPROVAL)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onTransferRequested_setsPendingApprovalStatus() {
        repository.onTransferRequested(new FileTransferRequest("photo.jpg", 4_194_304L));

        assertEquals(FileTransferStatus.PENDING_APPROVAL, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferRequested_storesFileNameAndSize() {
        FileTransferRequest request = new FileTransferRequest("document.pdf", 1_048_576L);

        repository.onTransferRequested(request);

        FileTransferRequest stored = repository.getPendingRequest().getValue();
        assertNotNull(stored);
        assertEquals("document.pdf", stored.getFileName());
        assertEquals(1_048_576L, stored.getFileSizeBytes());
    }

    @Test
    public void onTransferRequested_notifiesIncomingRequestListener() {
        FileTransferRequest request = new FileTransferRequest("video.mp4", 102_400_000L);

        repository.onTransferRequested(request);

        verify(mockIncomingRequestListener).onRequestArrived(request);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onTransferAccepted  (PENDING_APPROVAL → RECEIVING)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onTransferAccepted_setsReceivingStatus() {
        repository.onTransferRequested(new FileTransferRequest("video.mp4", 102_400L));

        repository.onTransferAccepted();

        assertEquals(FileTransferStatus.RECEIVING, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferAccepted_callsListenerWithCorrectFileName() {
        repository.onTransferRequested(new FileTransferRequest("video.mp4", 102_400L));

        repository.onTransferAccepted();

        verify(mockActionListener).onUserAccepted("video.mp4");
    }

    @Test
    public void onTransferAccepted_doesNotCallOnUserRejected() {
        repository.onTransferRequested(new FileTransferRequest("video.mp4", 102_400L));

        repository.onTransferAccepted();

        verify(mockActionListener, never()).onUserRejected();
    }

    @Test
    public void onTransferAccepted_withNoListener_doesNotCrash() {
        // Arrange: no listener registered
        repository.setActionListener(null);
        repository.onTransferRequested(new FileTransferRequest("file.zip", 512L));

        // Should not throw NullPointerException
        repository.onTransferAccepted();

        assertEquals(FileTransferStatus.RECEIVING, repository.getTransferStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onTransferRejected  (PENDING_APPROVAL → REJECTED)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onTransferRejected_setsRejectedStatus() {
        repository.onTransferRequested(new FileTransferRequest("image.png", 2048L));

        repository.onTransferRejected();

        assertEquals(FileTransferStatus.REJECTED, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferRejected_clearsPendingRequest() {
        repository.onTransferRequested(new FileTransferRequest("image.png", 2048L));

        repository.onTransferRejected();

        assertNull(repository.getPendingRequest().getValue());
    }

    @Test
    public void onTransferRejected_callsListenerOnUserRejected() {
        repository.onTransferRequested(new FileTransferRequest("image.png", 2048L));

        repository.onTransferRejected();

        verify(mockActionListener).onUserRejected();
    }

    @Test
    public void onTransferRejected_doesNotCallOnUserAccepted() {
        repository.onTransferRequested(new FileTransferRequest("image.png", 2048L));

        repository.onTransferRejected();

        verify(mockActionListener, never()).onUserAccepted(anyString());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onTransferCompleted  (RECEIVING → COMPLETED)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onTransferCompleted_setsCompletedStatus() {
        repository.onTransferRequested(new FileTransferRequest("archive.zip", 8_192_000L));
        repository.onTransferAccepted();

        repository.onTransferCompleted();

        assertEquals(FileTransferStatus.COMPLETED, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferCompleted_clearsPendingRequest() {
        repository.onTransferRequested(new FileTransferRequest("archive.zip", 8_192_000L));
        repository.onTransferAccepted();

        repository.onTransferCompleted();

        assertNull(repository.getPendingRequest().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onTransferFailed  (any state → FAILED)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onTransferFailed_setsFailedStatus() {
        repository.onTransferRequested(new FileTransferRequest("data.bin", 65_536L));

        repository.onTransferFailed();

        assertEquals(FileTransferStatus.FAILED, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferFailed_clearsPendingRequest() {
        repository.onTransferRequested(new FileTransferRequest("data.bin", 65_536L));

        repository.onTransferFailed();

        assertNull(repository.getPendingRequest().getValue());
    }

    @Test
    public void onTransferFailed_fromReceivingState_setsFailedStatus() {
        // Failure can happen mid-transfer, not just at PENDING_APPROVAL
        repository.onTransferRequested(new FileTransferRequest("movie.mkv", 1_000_000_000L));
        repository.onTransferAccepted();

        repository.onTransferFailed();

        assertEquals(FileTransferStatus.FAILED, repository.getTransferStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // reset  (terminal state → IDLE)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void reset_afterCompleted_returnsToIdle() {
        repository.onTransferRequested(new FileTransferRequest("song.mp3", 5_000_000L));
        repository.onTransferAccepted();
        repository.onTransferCompleted();

        repository.reset();

        assertEquals(FileTransferStatus.IDLE, repository.getTransferStatus().getValue());
        assertNull(repository.getPendingRequest().getValue());
    }

    @Test
    public void reset_afterRejected_returnsToIdle() {
        repository.onTransferRequested(new FileTransferRequest("song.mp3", 5_000_000L));
        repository.onTransferRejected();

        repository.reset();

        assertEquals(FileTransferStatus.IDLE, repository.getTransferStatus().getValue());
    }

    @Test
    public void reset_afterFailed_returnsToIdle() {
        repository.onTransferRequested(new FileTransferRequest("song.mp3", 5_000_000L));
        repository.onTransferFailed();

        repository.reset();

        assertEquals(FileTransferStatus.IDLE, repository.getTransferStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Full lifecycle smoke test
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void fullHappyPath_idleThroughCompletedAndBackToIdle() {
        // IDLE
        assertEquals(FileTransferStatus.IDLE, repository.getTransferStatus().getValue());

        // PC sends metadata → PENDING_APPROVAL
        repository.onTransferRequested(new FileTransferRequest("backup.zip", 2_048_000L));
        assertEquals(FileTransferStatus.PENDING_APPROVAL, repository.getTransferStatus().getValue());

        // User accepts → RECEIVING
        repository.onTransferAccepted();
        assertEquals(FileTransferStatus.RECEIVING, repository.getTransferStatus().getValue());

        // All bytes saved → COMPLETED
        repository.onTransferCompleted();
        assertEquals(FileTransferStatus.COMPLETED, repository.getTransferStatus().getValue());

        // UI acknowledges → IDLE
        repository.reset();
        assertEquals(FileTransferStatus.IDLE, repository.getTransferStatus().getValue());
    }
}

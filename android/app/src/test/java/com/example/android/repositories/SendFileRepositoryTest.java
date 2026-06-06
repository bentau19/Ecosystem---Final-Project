package com.example.android.repositories;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import android.net.Uri;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;

import com.example.android.domain.enums.SendFileStatus;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.mockito.Mock;
import org.mockito.junit.MockitoJUnitRunner;

import java.lang.reflect.Field;

/**
 * Unit tests for SendFileRepository — verifies all state-machine transitions
 * and listener callbacks. Same reflection-based singleton reset pattern as
 * ReceiveFileRepositoryTest.
 */
@RunWith(MockitoJUnitRunner.class)
public class SendFileRepositoryTest {

    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    @Mock
    private SendFileRepository.SendFileActionListener mockActionListener;

    @Mock
    private Uri mockUri;

    private SendFileRepository repository;

    @Before
    public void setUp() throws Exception {
        Field instanceField = SendFileRepository.class.getDeclaredField("instance");
        instanceField.setAccessible(true);
        instanceField.set(null, null);

        repository = SendFileRepository.getInstance();
        repository.setActionListener(mockActionListener);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Initial state
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void initialState_statusIsIdle() {
        assertEquals(SendFileStatus.IDLE, repository.getSendStatus().getValue());
    }

    @Test
    public void initialState_fileNameIsNull() {
        assertNull(repository.getCurrentFileName().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // requestSend  (IDLE → WAITING_FOR_RESPONSE)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void requestSend_setsWaitingForResponseStatus() {
        repository.requestSend(mockUri, "photo.jpg");

        assertEquals(SendFileStatus.WAITING_FOR_RESPONSE, repository.getSendStatus().getValue());
    }

    @Test
    public void requestSend_storesFileName() {
        repository.requestSend(mockUri, "report.pdf");

        assertEquals("report.pdf", repository.getCurrentFileName().getValue());
    }

    @Test
    public void requestSend_callsActionListenerWithUri() {
        repository.requestSend(mockUri, "video.mp4");

        verify(mockActionListener).onSendRequested(mockUri);
    }

    @Test
    public void requestSend_withNoListener_setsFailedStatus() {
        repository.setActionListener(null);

        repository.requestSend(mockUri, "file.zip");

        assertEquals(SendFileStatus.FAILED, repository.getSendStatus().getValue());
    }

    @Test
    public void requestSend_withNoListener_doesNotCrash() {
        // Should not throw NullPointerException
        repository.setActionListener(null);
        repository.requestSend(mockUri, "file.zip");
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onSendStarted  (WAITING_FOR_RESPONSE → SENDING)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onSendStarted_setsSendingStatus() {
        repository.requestSend(mockUri, "photo.jpg");

        repository.onSendStarted();

        assertEquals(SendFileStatus.SENDING, repository.getSendStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onSendCompleted  (SENDING → COMPLETED)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onSendCompleted_setsCompletedStatus() {
        repository.requestSend(mockUri, "photo.jpg");
        repository.onSendStarted();

        repository.onSendCompleted();

        assertEquals(SendFileStatus.COMPLETED, repository.getSendStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onSendRejected  (WAITING_FOR_RESPONSE → REJECTED)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onSendRejected_setsRejectedStatus() {
        repository.requestSend(mockUri, "photo.jpg");

        repository.onSendRejected();

        assertEquals(SendFileStatus.REJECTED, repository.getSendStatus().getValue());
    }

    @Test
    public void onSendRejected_clearsFileName() {
        repository.requestSend(mockUri, "photo.jpg");

        repository.onSendRejected();

        assertNull(repository.getCurrentFileName().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onSendFailed  (any state → FAILED)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onSendFailed_setsFailedStatus() {
        repository.requestSend(mockUri, "photo.jpg");

        repository.onSendFailed();

        assertEquals(SendFileStatus.FAILED, repository.getSendStatus().getValue());
    }

    @Test
    public void onSendFailed_clearsFileName() {
        repository.requestSend(mockUri, "photo.jpg");

        repository.onSendFailed();

        assertNull(repository.getCurrentFileName().getValue());
    }

    @Test
    public void onSendFailed_fromSendingState_setsFailedStatus() {
        repository.requestSend(mockUri, "video.mkv");
        repository.onSendStarted();

        repository.onSendFailed();

        assertEquals(SendFileStatus.FAILED, repository.getSendStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // reset  (terminal state → IDLE)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void reset_afterCompleted_returnsToIdle() {
        repository.requestSend(mockUri, "song.mp3");
        repository.onSendStarted();
        repository.onSendCompleted();

        repository.reset();

        assertEquals(SendFileStatus.IDLE, repository.getSendStatus().getValue());
    }

    @Test
    public void reset_afterRejected_returnsToIdle() {
        repository.requestSend(mockUri, "song.mp3");
        repository.onSendRejected();

        repository.reset();

        assertEquals(SendFileStatus.IDLE, repository.getSendStatus().getValue());
    }

    @Test
    public void reset_afterFailed_returnsToIdle() {
        repository.requestSend(mockUri, "song.mp3");
        repository.onSendFailed();

        repository.reset();

        assertEquals(SendFileStatus.IDLE, repository.getSendStatus().getValue());
    }

    @Test
    public void reset_clearsFileName() {
        repository.requestSend(mockUri, "song.mp3");
        repository.onSendCompleted();

        repository.reset();

        assertNull(repository.getCurrentFileName().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Full lifecycle smoke test
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void fullHappyPath_idleThroughCompletedAndBackToIdle() {
        // IDLE
        assertEquals(SendFileStatus.IDLE, repository.getSendStatus().getValue());

        // User shares file → WAITING_FOR_RESPONSE
        repository.requestSend(mockUri, "backup.zip");
        assertEquals(SendFileStatus.WAITING_FOR_RESPONSE, repository.getSendStatus().getValue());
        verify(mockActionListener).onSendRequested(mockUri);

        // PC accepted → SENDING
        repository.onSendStarted();
        assertEquals(SendFileStatus.SENDING, repository.getSendStatus().getValue());

        // All bytes sent → COMPLETED
        repository.onSendCompleted();
        assertEquals(SendFileStatus.COMPLETED, repository.getSendStatus().getValue());

        // UI acknowledged → IDLE
        repository.reset();
        assertEquals(SendFileStatus.IDLE, repository.getSendStatus().getValue());
        assertNull(repository.getCurrentFileName().getValue());
    }

    @Test
    public void rejectedPath_waitingThroughRejectedAndBackToIdle() {
        repository.requestSend(mockUri, "photo.jpg");
        assertEquals(SendFileStatus.WAITING_FOR_RESPONSE, repository.getSendStatus().getValue());

        repository.onSendRejected();
        assertEquals(SendFileStatus.REJECTED, repository.getSendStatus().getValue());

        repository.reset();
        assertEquals(SendFileStatus.IDLE, repository.getSendStatus().getValue());
    }
}

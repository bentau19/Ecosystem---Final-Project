package com.example.android.repositories;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;

import com.example.android.domain.enums.WebcamStatus;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.mockito.Mock;
import org.mockito.junit.MockitoJUnitRunner;

import java.lang.reflect.Field;

/**
 * Unit tests for WebcamRepository — verifies all state-machine transitions
 * and StreamActionListener callbacks.
 *
 * Uses the same reflection-based singleton reset pattern as SendFileRepositoryTest
 * to guarantee full isolation between tests.
 */
@RunWith(MockitoJUnitRunner.class)
public class WebcamRepositoryTest {

    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    @Mock
    private WebcamRepository.StreamActionListener mockActionListener;

    private WebcamRepository repository;

    @Before
    public void setUp() throws Exception {
        Field instanceField = WebcamRepository.class.getDeclaredField("instance");
        instanceField.setAccessible(true);
        instanceField.set(null, null);

        repository = WebcamRepository.getInstance();
        repository.setActionListener(mockActionListener);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Initial state
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void initialState_statusIsIdle() {
        assertEquals(WebcamStatus.IDLE, repository.getStatus().getValue());
    }

    @Test
    public void initialState_frameQueueIsEmpty() {
        assertTrue(repository.frameQueue.isEmpty());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // requestStart  (IDLE → STREAMING)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void requestStart_setsStreamingStatus() {
        repository.requestStart();

        assertEquals(WebcamStatus.STREAMING, repository.getStatus().getValue());
    }

    @Test
    public void requestStart_callsOnStartRequested() {
        repository.requestStart();

        verify(mockActionListener).onStartRequested();
    }

    @Test
    public void requestStart_withNoListener_setsFailed() {
        repository.setActionListener(null);

        repository.requestStart();

        assertEquals(WebcamStatus.FAILED, repository.getStatus().getValue());
    }

    @Test
    public void requestStart_withNoListener_doesNotCrash() {
        repository.setActionListener(null);
        repository.requestStart(); // must not throw NPE
    }

    // ─────────────────────────────────────────────────────────────────────────
    // requestStop
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void requestStop_callsOnStopRequested() {
        repository.requestStart();

        repository.requestStop();

        verify(mockActionListener).onStopRequested();
    }

    @Test
    public void requestStop_withNoListener_doesNotCrash() {
        repository.setActionListener(null);
        repository.requestStop(); // must not throw NPE
    }

    @Test
    public void requestStop_withNoListener_doesNotCallListener() {
        repository.setActionListener(null);

        repository.requestStop();

        verify(mockActionListener, never()).onStopRequested();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onStreamStopped  (STREAMING → STOPPED)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onStreamStopped_setsStoppedStatus() {
        repository.requestStart();

        repository.onStreamStopped();

        assertEquals(WebcamStatus.STOPPED, repository.getStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onStreamFailed  (any state → FAILED)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onStreamFailed_setsFailedStatus() {
        repository.requestStart();

        repository.onStreamFailed();

        assertEquals(WebcamStatus.FAILED, repository.getStatus().getValue());
    }

    @Test
    public void onStreamFailed_fromIdleState_setsFailedStatus() {
        repository.onStreamFailed();

        assertEquals(WebcamStatus.FAILED, repository.getStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // reset  (terminal state → IDLE)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void reset_afterStopped_returnsToIdle() {
        repository.requestStart();
        repository.onStreamStopped();

        repository.reset();

        assertEquals(WebcamStatus.IDLE, repository.getStatus().getValue());
    }

    @Test
    public void reset_afterFailed_returnsToIdle() {
        repository.requestStart();
        repository.onStreamFailed();

        repository.reset();

        assertEquals(WebcamStatus.IDLE, repository.getStatus().getValue());
    }

    @Test
    public void reset_clearsFrameQueue() throws InterruptedException {
        repository.frameQueue.offer(new byte[]{1, 2, 3});
        repository.frameQueue.offer(new byte[]{4, 5, 6});

        repository.reset();

        assertTrue(repository.frameQueue.isEmpty());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Full lifecycle smoke test
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void happyPath_idleThroughStoppedAndBackToIdle() {
        // IDLE
        assertEquals(WebcamStatus.IDLE, repository.getStatus().getValue());

        // User taps Start → STREAMING
        repository.requestStart();
        assertEquals(WebcamStatus.STREAMING, repository.getStatus().getValue());
        verify(mockActionListener).onStartRequested();

        // User taps Stop → listener is notified
        repository.requestStop();
        verify(mockActionListener).onStopRequested();

        // UseCase closes channel → STOPPED
        repository.onStreamStopped();
        assertEquals(WebcamStatus.STOPPED, repository.getStatus().getValue());

        // UI resets → IDLE
        repository.reset();
        assertEquals(WebcamStatus.IDLE, repository.getStatus().getValue());
    }

    @Test
    public void failurePath_streamingThroughFailedAndBackToIdle() {
        repository.requestStart();
        assertEquals(WebcamStatus.STREAMING, repository.getStatus().getValue());

        repository.onStreamFailed();
        assertEquals(WebcamStatus.FAILED, repository.getStatus().getValue());

        repository.reset();
        assertEquals(WebcamStatus.IDLE, repository.getStatus().getValue());
    }
}

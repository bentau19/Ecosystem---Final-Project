package com.example.android.viewmodel;

import static org.junit.Assert.assertEquals;
import static org.mockito.Mockito.lenient;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;

import com.example.android.domain.enums.WebcamStatus;
import com.example.android.repositories.SettingsRepository;
import com.example.android.repositories.WebcamRepository;

import org.junit.After;
import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.mockito.Mock;
import org.mockito.junit.MockitoJUnitRunner;

import java.lang.reflect.Field;

/**
 * Unit tests for WebcamViewModel.
 *
 * WebcamViewModel is a thin delegation layer over WebcamRepository.getInstance(),
 * so the tests drive the real repository singleton and assert that the ViewModel's
 * exposed LiveData reflects state correctly. Singleton is reset via reflection
 * before each test (same pattern as FileTransferViewModelTest).
 */
@RunWith(MockitoJUnitRunner.class)
public class WebcamViewModelTest {

    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    @Mock
    private WebcamRepository.StreamActionListener mockActionListener;

    @Mock
    private SettingsRepository mockSettings;

    private WebcamViewModel viewModel;
    private WebcamRepository repository;

    @Before
    public void setUp() throws Exception {
        Field instanceField = WebcamRepository.class.getDeclaredField("instance");
        instanceField.setAccessible(true);
        instanceField.set(null, null);

        // startStream() now gates on SettingsRepository.getInstance().isWebcamEnabled(),
        // which throws if the singleton was never initialized via getInstance(Context).
        // Inject a mock that reports the webcam enabled so the lifecycle under test runs.
        // lenient(): initialState_statusIsIdle never calls startStream(), so the stub is
        // unused there and strict MockitoJUnitRunner would otherwise fail it.
        Field settingsField = SettingsRepository.class.getDeclaredField("instance");
        settingsField.setAccessible(true);
        settingsField.set(null, mockSettings);
        lenient().when(mockSettings.isWebcamEnabled()).thenReturn(true);

        repository = WebcamRepository.getInstance();
        repository.setActionListener(mockActionListener);
        viewModel = new WebcamViewModel();
    }

    @After
    public void tearDown() throws Exception {
        // Don't leak the injected mock into other test classes sharing this JVM.
        Field settingsField = SettingsRepository.class.getDeclaredField("instance");
        settingsField.setAccessible(true);
        settingsField.set(null, null);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Initial state
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void initialState_statusIsIdle() {
        assertEquals(WebcamStatus.IDLE, viewModel.getStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // startStream  (IDLE → STREAMING)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void startStream_statusBecomesStreaming() {
        viewModel.startStream();

        assertEquals(WebcamStatus.STREAMING, viewModel.getStatus().getValue());
    }

    @Test
    public void startStream_withNoListener_statusBecomesFailed() {
        repository.setActionListener(null);

        viewModel.startStream();

        assertEquals(WebcamStatus.FAILED, viewModel.getStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // stopStream
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void stopStream_doesNotCrash() {
        viewModel.startStream();
        viewModel.stopStream(); // must not throw
    }

    // ─────────────────────────────────────────────────────────────────────────
    // reset
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void reset_afterStopped_statusBecomesIdle() {
        viewModel.startStream();
        repository.onStreamStopped();

        viewModel.reset();

        assertEquals(WebcamStatus.IDLE, viewModel.getStatus().getValue());
    }

    @Test
    public void reset_afterFailed_statusBecomesIdle() {
        viewModel.startStream();
        repository.onStreamFailed();

        viewModel.reset();

        assertEquals(WebcamStatus.IDLE, viewModel.getStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // LiveData exposure — ViewModel is a transparent window onto the repository
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void getStatus_reflectsFullLifecycle() {
        assertEquals(WebcamStatus.IDLE, viewModel.getStatus().getValue());

        viewModel.startStream();
        assertEquals(WebcamStatus.STREAMING, viewModel.getStatus().getValue());

        repository.onStreamStopped();
        assertEquals(WebcamStatus.STOPPED, viewModel.getStatus().getValue());

        viewModel.reset();
        assertEquals(WebcamStatus.IDLE, viewModel.getStatus().getValue());
    }

    @Test
    public void getStatus_reflectsFailurePath() {
        viewModel.startStream();
        assertEquals(WebcamStatus.STREAMING, viewModel.getStatus().getValue());

        repository.onStreamFailed();
        assertEquals(WebcamStatus.FAILED, viewModel.getStatus().getValue());

        viewModel.reset();
        assertEquals(WebcamStatus.IDLE, viewModel.getStatus().getValue());
    }
}

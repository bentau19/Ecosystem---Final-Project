package com.example.android.viewmodel;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import android.net.Uri;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;

import com.example.android.domain.enums.SendFileStatus;
import com.example.android.repositories.SendFileRepository;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.mockito.Mock;
import org.mockito.junit.MockitoJUnitRunner;

import java.lang.reflect.Field;

/**
 * Unit tests for SendFileViewModel.
 *
 * Because SendFileViewModel delegates all logic to SendFileRepository.getInstance(),
 * these tests work with the real repository singleton — verifying that ViewModel
 * actions produce the expected LiveData state visible to the UI.
 *
 * A no-op SendFileActionListener is registered before each test so that
 * requestSend() reaches WAITING_FOR_RESPONSE without hitting the null-listener
 * FAILED branch, keeping tests focused on ViewModel delegation rather than
 * listener wiring (which is covered by SendFileRepositoryTest).
 *
 * The singleton is reset via reflection before each test to guarantee isolation.
 */
@RunWith(MockitoJUnitRunner.class)
public class SendFileViewModelTest {

    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    @Mock
    private Uri mockUri;

    private SendFileViewModel viewModel;
    private SendFileRepository repository;

    @Before
    public void setUp() throws Exception {
        Field instanceField = SendFileRepository.class.getDeclaredField("instance");
        instanceField.setAccessible(true);
        instanceField.set(null, null);

        repository = SendFileRepository.getInstance();

        // Register a no-op listener so requestSend() reaches WAITING_FOR_RESPONSE
        // without failing due to a missing ConnectivityService in the test environment.
        repository.setActionListener(uri -> { /* no-op */ });

        viewModel = new SendFileViewModel();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Initial state
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void initialState_statusIsIdle() {
        assertEquals(SendFileStatus.IDLE, viewModel.getSendStatus().getValue());
    }

    @Test
    public void initialState_fileNameIsNull() {
        assertNull(viewModel.getCurrentFileName().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // sendFile
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void sendFile_statusBecomesWaitingForResponse() {
        viewModel.sendFile(mockUri, "photo.jpg");

        assertEquals(SendFileStatus.WAITING_FOR_RESPONSE, viewModel.getSendStatus().getValue());
    }

    @Test
    public void sendFile_exposesFileName() {
        viewModel.sendFile(mockUri, "report.pdf");

        assertEquals("report.pdf", viewModel.getCurrentFileName().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // reset
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void reset_afterCompleted_statusBecomesIdle() {
        repository.requestSend(mockUri, "video.mp4");
        repository.onSendCompleted();

        viewModel.reset();

        assertEquals(SendFileStatus.IDLE, viewModel.getSendStatus().getValue());
    }

    @Test
    public void reset_afterRejected_statusBecomesIdle() {
        repository.requestSend(mockUri, "video.mp4");
        repository.onSendRejected();

        viewModel.reset();

        assertEquals(SendFileStatus.IDLE, viewModel.getSendStatus().getValue());
    }

    @Test
    public void reset_afterFailed_statusBecomesIdle() {
        repository.requestSend(mockUri, "video.mp4");
        repository.onSendFailed();

        viewModel.reset();

        assertEquals(SendFileStatus.IDLE, viewModel.getSendStatus().getValue());
    }

    @Test
    public void reset_clearsFileName() {
        repository.requestSend(mockUri, "doc.pdf");
        repository.onSendCompleted();

        viewModel.reset();

        assertNull(viewModel.getCurrentFileName().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // LiveData exposure — ViewModel is a transparent window onto the Repository
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void getSendStatus_reflectsFullLifecycle() {
        assertEquals(SendFileStatus.IDLE, viewModel.getSendStatus().getValue());

        repository.requestSend(mockUri, "backup.zip");
        assertEquals(SendFileStatus.WAITING_FOR_RESPONSE, viewModel.getSendStatus().getValue());

        repository.onSendStarted();
        assertEquals(SendFileStatus.SENDING, viewModel.getSendStatus().getValue());

        repository.onSendCompleted();
        assertEquals(SendFileStatus.COMPLETED, viewModel.getSendStatus().getValue());

        viewModel.reset();
        assertEquals(SendFileStatus.IDLE, viewModel.getSendStatus().getValue());
    }

    @Test
    public void getCurrentFileName_reflectsRepository() {
        assertNull(viewModel.getCurrentFileName().getValue());

        repository.requestSend(mockUri, "archive.zip");
        assertEquals("archive.zip", viewModel.getCurrentFileName().getValue());

        repository.onSendCompleted();
        viewModel.reset();
        assertNull(viewModel.getCurrentFileName().getValue());
    }
}

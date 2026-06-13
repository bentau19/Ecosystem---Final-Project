package com.example.android.repositories;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;

import com.example.android.domain.entities.BackupFileEntry;
import com.example.android.domain.entities.BackupOptions;
import com.example.android.domain.enums.BackupScanStatus;
import com.example.android.domain.enums.BackupTransferStatus;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.mockito.Mock;
import org.mockito.junit.MockitoJUnitRunner;

import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * Unit tests for BackupRepository — covers the full scan and transfer state machines,
 * the scanActiveForTransfer guard, control routing, and all LiveData transitions.
 *
 * Uses the same reflection-based singleton reset pattern as DeviceRepositoryTest.
 */
@RunWith(MockitoJUnitRunner.class)
public class BackupRepositoryTest {

    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    @Mock
    private BackupRepository.ScanActionListener mockScanActionListener;

    @Mock
    private BackupRepository.TransferActionListener mockTransferActionListener;

    @Mock
    private BackupRepository.ControlActionListener mockControlActionListener;

    private BackupRepository repository;

    @Before
    public void setUp() throws Exception {
        Field instanceField = BackupRepository.class.getDeclaredField("instance");
        instanceField.setAccessible(true);
        instanceField.set(null, null);

        repository = BackupRepository.getInstance();
        repository.setActionListener(mockScanActionListener);
        repository.setTransferActionListener(mockTransferActionListener);
        repository.setControlActionListener(mockControlActionListener);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────────────────────────────────

    private static BackupFileEntry makeEntry(String name) {
        return new BackupFileEntry(
                "/storage/emulated/0/" + name,
                1024L,
                1_000_000L,
                "content://media/" + name,
                "uuid-" + name
        );
    }

    private static List<BackupFileEntry> singleFile() {
        return Collections.singletonList(makeEntry("photo.jpg"));
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Initial state
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void initialState_scanStatusIsIdle() {
        assertEquals(BackupScanStatus.IDLE, repository.getScanStatus().getValue());
    }

    @Test
    public void initialState_transferStatusIsIdle() {
        assertEquals(BackupTransferStatus.IDLE, repository.getTransferStatus().getValue());
    }

    @Test
    public void initialState_countersAreZero() {
        assertEquals(Integer.valueOf(0), repository.getTransferSent().getValue());
        assertEquals(Integer.valueOf(0), repository.getTransferTotal().getValue());
        assertEquals(Integer.valueOf(0), repository.getFailedCount().getValue());
    }

    @Test
    public void initialState_scannedFilesIsEmpty() {
        assertNotNull(repository.getScannedFiles().getValue());
        assertTrue(repository.getScannedFiles().getValue().isEmpty());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // requestScan
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void requestScan_setsScanningStatus() {
        repository.requestScan("all_media", null, new BackupOptions(true));

        assertEquals(BackupScanStatus.SCANNING, repository.getScanStatus().getValue());
    }

    @Test
    public void requestScan_callsScanActionListenerWithMode() {
        repository.requestScan("all_media", null, new BackupOptions(true));

        verify(mockScanActionListener).onScanRequested(eq("all_media"), any());
    }

    @Test
    public void requestScan_withNoListener_setsFailed() {
        repository.setActionListener(null);

        repository.requestScan("all_media", null, new BackupOptions(true));

        assertEquals(BackupScanStatus.FAILED, repository.getScanStatus().getValue());
    }

    @Test
    public void requestScan_whileAlreadyScanning_isIgnored() {
        repository.requestScan("all_media", null, new BackupOptions(true));

        repository.requestScan("all_media", null, new BackupOptions(false));

        verify(mockScanActionListener, times(1)).onScanRequested(anyString(), any());
    }

    @Test
    public void requestScan_whileTransferIsSending_isIgnored() {
        // Bring transfer to SENDING
        repository.requestScan("all_media", null, new BackupOptions(true));
        repository.onScanComplete(singleFile());

        // Reset scan status so isBackupActive() depends solely on transfer
        // (onScanComplete posts IDLE for scanStatus)
        assertEquals(BackupTransferStatus.SENDING, repository.getTransferStatus().getValue());

        // Attempt second scan
        repository.requestScan("all_media", null, new BackupOptions(false));

        // actionListener called only once (from the first requestScan)
        verify(mockScanActionListener, times(1)).onScanRequested(anyString(), any());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // isBackupActive
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void isBackupActive_whenIdle_returnsFalse() {
        assertFalse(repository.isBackupActive());
    }

    @Test
    public void isBackupActive_whenScanning_returnsTrue() {
        repository.requestScan("all_media", null, new BackupOptions(true));

        assertTrue(repository.isBackupActive());
    }

    @Test
    public void isBackupActive_whenTransferSending_returnsTrue() {
        repository.requestScan("all_media", null, new BackupOptions(true));
        repository.onScanComplete(singleFile());

        assertTrue(repository.isBackupActive());
    }

    @Test
    public void isBackupActive_whenTransferPaused_returnsTrue() {
        repository.requestScan("all_media", null, new BackupOptions(true));
        repository.onScanComplete(singleFile());
        repository.onTransferPaused();

        assertTrue(repository.isBackupActive());
    }

    @Test
    public void isBackupActive_afterTransferComplete_returnsFalse() {
        repository.requestScan("all_media", null, new BackupOptions(true));
        repository.onScanComplete(singleFile());
        repository.onTransferComplete();

        assertFalse(repository.isBackupActive());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onScanComplete
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onScanComplete_updatesScannedFiles() {
        repository.requestScan("all_media", null, new BackupOptions(true));
        List<BackupFileEntry> files = singleFile();

        repository.onScanComplete(files);

        assertEquals(files, repository.getScannedFiles().getValue());
    }

    @Test
    public void onScanComplete_withNonEmptyList_setsScanStatusIdle() {
        repository.requestScan("all_media", null, new BackupOptions(true));

        repository.onScanComplete(singleFile());

        assertEquals(BackupScanStatus.IDLE, repository.getScanStatus().getValue());
    }

    @Test
    public void onScanComplete_withNonEmptyList_autoTriggersTransfer() {
        repository.requestScan("all_media", null, new BackupOptions(true));
        List<BackupFileEntry> files = singleFile();

        repository.onScanComplete(files);

        assertEquals(BackupTransferStatus.SENDING, repository.getTransferStatus().getValue());
        verify(mockTransferActionListener).onTransferRequested(eq(files), any(BackupOptions.class));
    }

    @Test
    public void onScanComplete_withEmptyList_setsScanStatusEmpty() {
        repository.requestScan("all_media", null, new BackupOptions(true));

        repository.onScanComplete(Collections.emptyList());

        assertEquals(BackupScanStatus.EMPTY, repository.getScanStatus().getValue());
    }

    @Test
    public void onScanComplete_withEmptyList_doesNotTriggerTransfer() {
        repository.requestScan("all_media", null, new BackupOptions(true));

        repository.onScanComplete(Collections.emptyList());

        assertEquals(BackupTransferStatus.IDLE, repository.getTransferStatus().getValue());
        verify(mockTransferActionListener, never()).onTransferRequested(any(), any());
    }

    @Test
    public void onScanComplete_afterReset_guardDiscardsScanResult() {
        // Simulate: scan started, connection dropped, reset() clears the guard
        repository.requestScan("all_media", null, new BackupOptions(true));
        repository.reset(); // scanActiveForTransfer → false

        repository.onScanComplete(singleFile());

        // Transfer must NOT be triggered for a stale session
        assertEquals(BackupTransferStatus.IDLE, repository.getTransferStatus().getValue());
        verify(mockTransferActionListener, never()).onTransferRequested(any(), any());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // onScanFailed
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onScanFailed_setsScanStatusFailed() {
        repository.requestScan("all_media", null, new BackupOptions(true));

        repository.onScanFailed();

        assertEquals(BackupScanStatus.FAILED, repository.getScanStatus().getValue());
    }

    @Test
    public void onScanFailed_clearsScannedFiles() {
        repository.requestScan("all_media", null, new BackupOptions(true));

        repository.onScanFailed();

        assertTrue(repository.getScannedFiles().getValue().isEmpty());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // reset (scan)
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void reset_setsScanStatusIdle() {
        repository.requestScan("all_media", null, new BackupOptions(true));

        repository.reset();

        assertEquals(BackupScanStatus.IDLE, repository.getScanStatus().getValue());
    }

    @Test
    public void reset_clearsScannedFiles() {
        repository.requestScan("all_media", null, new BackupOptions(true));
        repository.onScanComplete(singleFile());
        repository.reset();

        assertTrue(repository.getScannedFiles().getValue().isEmpty());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // requestTransfer
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void requestTransfer_setsTransferStatusSending() {
        repository.requestTransfer(singleFile(), new BackupOptions(true));

        assertEquals(BackupTransferStatus.SENDING, repository.getTransferStatus().getValue());
    }

    @Test
    public void requestTransfer_setsTransferTotal() {
        List<BackupFileEntry> files = Arrays.asList(makeEntry("a.jpg"), makeEntry("b.jpg"));

        repository.requestTransfer(files, new BackupOptions(true));

        assertEquals(Integer.valueOf(2), repository.getTransferTotal().getValue());
    }

    @Test
    public void requestTransfer_resetsSentCounterToZero() {
        repository.requestTransfer(singleFile(), new BackupOptions(true));

        assertEquals(Integer.valueOf(0), repository.getTransferSent().getValue());
    }

    @Test
    public void requestTransfer_withEmptyList_isNoop() {
        repository.requestTransfer(Collections.emptyList(), new BackupOptions(true));

        assertEquals(BackupTransferStatus.IDLE, repository.getTransferStatus().getValue());
        verify(mockTransferActionListener, never()).onTransferRequested(any(), any());
    }

    @Test
    public void requestTransfer_withNoListener_setsFailed() {
        repository.setTransferActionListener(null);

        repository.requestTransfer(singleFile(), new BackupOptions(true));

        assertEquals(BackupTransferStatus.FAILED, repository.getTransferStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Transfer progress — onFileTransferred / onFileResult
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onFileTransferred_updatesSentAndTotal() {
        repository.onFileTransferred(3, 10);

        assertEquals(Integer.valueOf(3), repository.getTransferSent().getValue());
        assertEquals(Integer.valueOf(10), repository.getTransferTotal().getValue());
    }

    @Test
    public void onFileResult_successDoesNotIncrementFailedCount() {
        repository.onFileResult(1, 5, true);

        assertEquals(Integer.valueOf(0), repository.getFailedCount().getValue());
    }

    @Test
    public void onFileResult_failureIncrementsFailedCount() {
        repository.onFileResult(1, 5, false);

        assertEquals(Integer.valueOf(1), repository.getFailedCount().getValue());
    }

    @Test
    public void onFileResult_multipleFailures_accumulates() {
        repository.onFileResult(1, 5, false);
        repository.onFileResult(2, 5, false);
        repository.onFileResult(3, 5, true);

        assertEquals(Integer.valueOf(2), repository.getFailedCount().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Transfer state transitions
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void onTransferComplete_setsCompleted() {
        repository.onTransferComplete();

        assertEquals(BackupTransferStatus.COMPLETED, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferFailed_setsFailed() {
        repository.onTransferFailed();

        assertEquals(BackupTransferStatus.FAILED, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferPaused_setsPaused() {
        repository.onTransferPaused();

        assertEquals(BackupTransferStatus.PAUSED, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferResumed_setsSending() {
        repository.onTransferPaused();

        repository.onTransferResumed();

        assertEquals(BackupTransferStatus.SENDING, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferStopped_setsStopped() {
        repository.onTransferStopped();

        assertEquals(BackupTransferStatus.STOPPED, repository.getTransferStatus().getValue());
    }

    @Test
    public void onTransferCanceledByPc_setsCanceledByPc() {
        repository.onTransferCanceledByPc();

        assertEquals(BackupTransferStatus.CANCELED_BY_PC, repository.getTransferStatus().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Control routing — pause / resume / stop
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void requestPause_delegatesToControlListener() {
        repository.requestPause();

        verify(mockControlActionListener).onPauseRequested();
    }

    @Test
    public void requestResume_delegatesToControlListener() {
        repository.requestResume();

        verify(mockControlActionListener).onResumeRequested();
    }

    @Test
    public void requestStop_delegatesToControlListener() {
        repository.requestStop();

        verify(mockControlActionListener).onStopRequested();
    }

    @Test
    public void requestPause_withNoListener_doesNotCrash() {
        repository.setControlActionListener(null);
        repository.requestPause();
    }

    @Test
    public void requestResume_withNoListener_doesNotCrash() {
        repository.setControlActionListener(null);
        repository.requestResume();
    }

    @Test
    public void requestStop_withNoListener_doesNotCrash() {
        repository.setControlActionListener(null);
        repository.requestStop();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // resetTransfer
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void resetTransfer_returnsTransferStatusToIdle() {
        repository.onTransferComplete();

        repository.resetTransfer();

        assertEquals(BackupTransferStatus.IDLE, repository.getTransferStatus().getValue());
    }

    @Test
    public void resetTransfer_clearsAllCounters() {
        repository.onFileTransferred(3, 5);
        repository.onFileResult(1, 5, false);
        repository.onFileResult(2, 5, false);

        repository.resetTransfer();

        assertEquals(Integer.valueOf(0), repository.getTransferSent().getValue());
        assertEquals(Integer.valueOf(0), repository.getTransferTotal().getValue());
        assertEquals(Integer.valueOf(0), repository.getFailedCount().getValue());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Full scan → transfer lifecycle smoke test
    // ─────────────────────────────────────────────────────────────────────────

    @Test
    public void fullScanToTransferLifecycle() {
        // IDLE
        assertEquals(BackupScanStatus.IDLE, repository.getScanStatus().getValue());
        assertEquals(BackupTransferStatus.IDLE, repository.getTransferStatus().getValue());

        // User taps Start → SCANNING
        repository.requestScan("all_media", null, new BackupOptions(true));
        assertEquals(BackupScanStatus.SCANNING, repository.getScanStatus().getValue());

        // Scan complete → auto-triggers SENDING
        repository.onScanComplete(singleFile());
        assertEquals(BackupScanStatus.IDLE, repository.getScanStatus().getValue());
        assertEquals(BackupTransferStatus.SENDING, repository.getTransferStatus().getValue());

        // Files transferred
        repository.onFileTransferred(1, 1);
        assertEquals(Integer.valueOf(1), repository.getTransferSent().getValue());

        // All done → COMPLETED
        repository.onTransferComplete();
        assertEquals(BackupTransferStatus.COMPLETED, repository.getTransferStatus().getValue());

        // UI acknowledged → IDLE
        repository.resetTransfer();
        assertEquals(BackupTransferStatus.IDLE, repository.getTransferStatus().getValue());
    }
}

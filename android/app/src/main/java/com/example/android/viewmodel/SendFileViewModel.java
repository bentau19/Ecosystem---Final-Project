package com.example.android.viewmodel;

import android.net.Uri;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.domain.enums.SendFileStatus;
import com.example.android.repositories.SendFileRepository;

/**
 * ViewModel responsible for the outgoing file transfer feature (Android → PC).
 *
 * Responsibilities:
 * - Exposes LiveData for the UI to observe send status and filename
 * - Delegates user actions (send / reset) to the Repository
 *
 * What it does NOT do:
 * - Does not touch the network (that's SendFileUseCase's job)
 * - Does not open URIs or ContentResolver (that's SendFileUseCase's job)
 * - Does not know about channels, TauSync, or ConnectivityService
 *
 * Scoped to MainActivity — the same instance is used both when the share
 * Intent arrives and when the result Toast / dialog is shown.
 */
public class SendFileViewModel extends ViewModel {

    private final SendFileRepository repository = SendFileRepository.getInstance();

    // ============ Observers (UI → ViewModel → Repository) ============

    /**
     * @return LiveData with the current outgoing transfer status.
     *         UI observes this to show progress dialogs and result Toasts.
     */
    public LiveData<SendFileStatus> getSendStatus() {
        return repository.getSendStatus();
    }

    /**
     * @return LiveData with the display name of the file being sent.
     *         Null when no transfer is active.
     *         Used to personalise UI messages ("Sending photo.jpg…").
     */
    public LiveData<String> getCurrentFileName() {
        return repository.getCurrentFileName();
    }

    // ============ User Actions ============

    /**
     * Called when the user shares a file to our app via the Android share sheet.
     * Transitions status to WAITING_FOR_RESPONSE and fires the ActionListener
     * so ConnectivityService can start the send protocol on a background thread.
     *
     * @param uri      Content URI of the file chosen by the user (from EXTRA_STREAM).
     * @param fileName Display name shown in the UI while waiting for PC response.
     */
    public void sendFile(Uri uri, String fileName) {
        repository.requestSend(uri, fileName);
    }

    /**
     * Called by the UI after it has acknowledged a terminal state
     * (COMPLETED / REJECTED / FAILED) — resets to IDLE ready for the next transfer.
     */
    public void reset() {
        repository.reset();
    }
}

package com.example.android.viewmodel;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.domain.entities.ReceiveFileRequest;
import com.example.android.domain.enums.ReceiveFileStatus;
import com.example.android.repositories.ReceiveFileRepository;

/**
 * ViewModel responsible for the incoming file transfer feature (PC → Android).
 *
 * Responsibilities:
 * - Exposes LiveData for the UI to observe transfer state
 * - Delegates user actions (accept / reject / reset) to the Repository
 *
 * What it does NOT do:
 * - Does not read from the network (that's the Handler's job)
 * - Does not write bytes to storage (that's the UseCase's job)
 * - Does not know about Android Context, channels, or TauSync
 *
 * Scoped to MainActivity — both the dialog (foreground) and the
 * notification action receiver (background) share this same instance.
 */
public class FileTransferViewModel extends ViewModel {

    private final ReceiveFileRepository repository = ReceiveFileRepository.getInstance();

    // ============ Observers (UI → ViewModel → Repository) ============

    /**
     * @return LiveData with the current incoming file transfer request.
     * Null = no active request. UI observes this to show the approval dialog.
     */
    public LiveData<ReceiveFileRequest> getPendingRequest() {
        return repository.getPendingRequest();
    }

    /**
     * @return LiveData with the current transfer lifecycle status.
     * UI observes this to show progress, completion, or error feedback.
     */
    public LiveData<ReceiveFileStatus> getTransferStatus() {
        return repository.getTransferStatus();
    }

    // ============ User Actions ============

    /**
     * Called when the user taps "Accept" in the dialog or notification.
     * Transitions state to RECEIVING — the UseCase will handle the actual byte stream.
     */
    public void acceptTransfer() {
        repository.onTransferAccepted();
    }

    /**
     * Called when the user taps "Reject" in the dialog or notification.
     * Transitions state to REJECTED and clears the pending request.
     */
    public void rejectTransfer() {
        repository.onTransferRejected();
    }

    /**
     * Called by the UI after it has acknowledged a terminal state
     * (COMPLETED / REJECTED / FAILED) — resets to IDLE for next transfer.
     */
    public void reset() {
        repository.reset();
    }
}

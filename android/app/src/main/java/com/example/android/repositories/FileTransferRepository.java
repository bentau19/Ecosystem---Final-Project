package com.example.android.repositories;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.domain.entities.FileTransferRequest;
import com.example.android.domain.enums.FileTransferStatus;

import android.util.Log;

/**
 * Repository responsible solely for incoming file transfer state (PC → Android).
 *
 * Single Responsibility: tracks the lifecycle of one incoming file transfer at a time.
 * Future repositories (ClipboardRepository, etc.) will follow the same pattern.
 *
 * Lifecycle of a transfer:
 *   IDLE → PENDING_APPROVAL → RECEIVING → COMPLETED
 *                           ↘ REJECTED
 *                  (any state) → FAILED
 *
 * ConnectivityService registers a FileTransferActionListener to receive Accept/Reject
 * callbacks — this keeps the ViewModel free of any transport knowledge.
 */
public class FileTransferRepository {

    private static FileTransferRepository instance;
    private static final String TAG = "FileTransferRepository";

    // The incoming file request (null when no transfer is active)
    private final MutableLiveData<FileTransferRequest> pendingRequest = new MutableLiveData<>(null);

    // The current lifecycle status of the transfer
    private final MutableLiveData<FileTransferStatus> transferStatus = new MutableLiveData<>(FileTransferStatus.IDLE);

    // Registered by ConnectivityService — bridges user decisions to network operations
    private FileTransferActionListener actionListener;

    /**
     * Callback interface implemented by ConnectivityService.
     * Keeps the ViewModel and Repository free of TransportManager knowledge.
     */
    public interface FileTransferActionListener {
        /** User tapped Accept — send ACCEPT to channel and start receiving bytes. */
        void onUserAccepted(String fileName);
        /** User tapped Reject — send REJECT to channel. */
        void onUserRejected();
    }

    private FileTransferRepository() {}

    public static synchronized FileTransferRepository getInstance() {
        if (instance == null) {
            instance = new FileTransferRepository();
        }
        return instance;
    }

    /**
     * Registered by ConnectivityService once the transport is ready.
     * Called when the user makes an Accept/Reject decision.
     */
    public void setActionListener(FileTransferActionListener listener) {
        this.actionListener = listener;
    }

    // ============ Observers (for ViewModel) ============

    public LiveData<FileTransferRequest> getPendingRequest() {
        return pendingRequest;
    }

    public LiveData<FileTransferStatus> getTransferStatus() {
        return transferStatus;
    }

    // ============ State Transitions (called by UseCases / Handlers) ============

    /**
     * Called by FileMetadataChannelHandler when the PC pushes file metadata.
     * IDLE → PENDING_APPROVAL
     */
    public void onTransferRequested(FileTransferRequest request) {
        Log.d(TAG, "Incoming transfer: " + request.getFileName() + " (" + request.getFormattedSize() + ")");
        pendingRequest.postValue(request);
        transferStatus.postValue(FileTransferStatus.PENDING_APPROVAL);
    }

    /**
     * Called by FileTransferViewModel when the user taps Accept.
     * Notifies ConnectivityService via listener to send ACCEPT and start receiving bytes.
     * PENDING_APPROVAL → RECEIVING
     */
    public void onTransferAccepted() {
        Log.d(TAG, "Transfer accepted by user");
        transferStatus.postValue(FileTransferStatus.RECEIVING);
        FileTransferRequest request = pendingRequest.getValue();
        if (actionListener != null && request != null) {
            actionListener.onUserAccepted(request.getFileName());
        } else {
            Log.w(TAG, "No actionListener or pending request on accept");
        }
    }

    /**
     * Called by FileTransferViewModel when the user taps Reject.
     * Notifies ConnectivityService via listener to send REJECT.
     * PENDING_APPROVAL → REJECTED
     */
    public void onTransferRejected() {
        Log.d(TAG, "Transfer rejected by user");
        pendingRequest.postValue(null);
        transferStatus.postValue(FileTransferStatus.REJECTED);
        if (actionListener != null) {
            actionListener.onUserRejected();
        } else {
            Log.w(TAG, "No actionListener registered on reject");
        }
    }

    /**
     * Called by ReceiveFileUseCase when all bytes are saved to storage.
     * RECEIVING → COMPLETED
     */
    public void onTransferCompleted() {
        Log.d(TAG, "Transfer completed");
        pendingRequest.postValue(null);
        transferStatus.postValue(FileTransferStatus.COMPLETED);
    }

    /**
     * Called by ReceiveFileUseCase on any network or I/O error.
     * ANY → FAILED
     */
    public void onTransferFailed() {
        Log.e(TAG, "Transfer failed");
        pendingRequest.postValue(null);
        transferStatus.postValue(FileTransferStatus.FAILED);
    }

    /**
     * Resets to IDLE after the UI has acknowledged the terminal state
     * (COMPLETED / REJECTED / FAILED).
     */
    public void reset() {
        pendingRequest.postValue(null);
        transferStatus.postValue(FileTransferStatus.IDLE);
    }
}

package com.example.android.repositories;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.domain.entities.ReceiveFileRequest;
import com.example.android.domain.enums.ReceiveFileStatus;

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
 * ConnectivityService registers a ReceiveFileActionListener to receive Accept/Reject
 * callbacks — this keeps the ViewModel free of any transport knowledge.
 */
public class ReceiveFileRepository {

    private static ReceiveFileRepository instance;
    private static final String TAG = "ReceiveFileRepository";

    // The incoming file request (null when no transfer is active)
    private final MutableLiveData<ReceiveFileRequest> pendingRequest = new MutableLiveData<>(null);

    // The current lifecycle status of the transfer
    private final MutableLiveData<ReceiveFileStatus> transferStatus = new MutableLiveData<>(ReceiveFileStatus.IDLE);

    // Registered by ConnectivityService — bridges user decisions to network operations
    private ReceiveFileActionListener actionListener;

    // Registered by ConnectivityService — fires immediately when a transfer request arrives
    // (bypasses LiveData lifecycle so the notification shows even when the app is in the background)
    private IncomingRequestListener incomingRequestListener;

    /**
     * Callback interface implemented by ConnectivityService.
     * Keeps the ViewModel and Repository free of TransportManager knowledge.
     */
    public interface ReceiveFileActionListener {
        /** User tapped Accept — send ACCEPT to channel and start receiving bytes. */
        void onUserAccepted(String fileName);
        /** User tapped Reject — send REJECT to channel. */
        void onUserRejected();
    }

    /**
     * Callback interface for being notified the moment a transfer request arrives,
     * regardless of whether the Activity is in the foreground.
     * Implemented by ConnectivityService to show a heads-up notification.
     */
    public interface IncomingRequestListener {
        void onRequestArrived(ReceiveFileRequest request);
    }

    private ReceiveFileRepository() {}

    public static synchronized ReceiveFileRepository getInstance() {
        if (instance == null) {
            instance = new ReceiveFileRepository();
        }
        return instance;
    }

    /**
     * Registered by ConnectivityService once the transport is ready.
     * Called when the user makes an Accept/Reject decision.
     */
    public void setActionListener(ReceiveFileActionListener listener) {
        this.actionListener = listener;
    }

    /**
     * Registered by ConnectivityService so it can show a notification immediately
     * when a transfer request arrives, even when the Activity is in the background.
     */
    public void setIncomingRequestListener(IncomingRequestListener listener) {
        this.incomingRequestListener = listener;
    }

    // ============ Observers (for ViewModel) ============

    public LiveData<ReceiveFileRequest> getPendingRequest() {
        return pendingRequest;
    }

    public LiveData<ReceiveFileStatus> getTransferStatus() {
        return transferStatus;
    }

    // ============ State Transitions (called by UseCases / Handlers) ============

    /**
     * Called by FileMetadataChannelHandler when the PC pushes file metadata.
     * IDLE → PENDING_APPROVAL
     */
    public void onTransferRequested(ReceiveFileRequest request) {
        Log.d(TAG, "Incoming transfer: " + request.getFileName() + " (" + request.getFormattedSize() + ")");
        // Post status BEFORE the request so that when MainActivity's pendingRequest observer
        // fires and reads transferStatus.getValue(), the status is already PENDING_APPROVAL.
        transferStatus.postValue(ReceiveFileStatus.PENDING_APPROVAL);
        pendingRequest.postValue(request);

        // Notify ConnectivityService immediately — this fires even when the Activity is in the
        // background (LiveData observers are paused for stopped Activities).
        if (incomingRequestListener != null) {
            incomingRequestListener.onRequestArrived(request);
        }
    }

    /**
     * Called by FileTransferViewModel when the user taps Accept.
     * Notifies ConnectivityService via listener to send ACCEPT and start receiving bytes.
     * PENDING_APPROVAL → RECEIVING
     */
    public void onTransferAccepted() {
        Log.d(TAG, "Transfer accepted by user");
        transferStatus.postValue(ReceiveFileStatus.RECEIVING);
        ReceiveFileRequest request = pendingRequest.getValue();
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
        transferStatus.postValue(ReceiveFileStatus.REJECTED);
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
        transferStatus.postValue(ReceiveFileStatus.COMPLETED);
    }

    /**
     * Called by ReceiveFileUseCase on any network or I/O error.
     * ANY → FAILED
     */
    public void onTransferFailed() {
        Log.e(TAG, "Transfer failed");
        pendingRequest.postValue(null);
        transferStatus.postValue(ReceiveFileStatus.FAILED);
    }

    /**
     * Resets to IDLE after the UI has acknowledged the terminal state
     * (COMPLETED / REJECTED / FAILED).
     */
    public void reset() {
        pendingRequest.postValue(null);
        transferStatus.postValue(ReceiveFileStatus.IDLE);
    }
}

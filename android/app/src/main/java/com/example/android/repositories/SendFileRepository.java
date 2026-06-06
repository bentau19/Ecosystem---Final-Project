package com.example.android.repositories;

import android.net.Uri;
import android.util.Log;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.domain.enums.SendFileStatus;

/**
 * Repository responsible solely for outgoing file transfer state (Android → PC).
 *
 * Single Responsibility: tracks the lifecycle of one outgoing file transfer at a time.
 * Mirrors ReceiveFileRepository — same singleton + LiveData + listener pattern.
 *
 * Lifecycle of a transfer:
 *   IDLE → WAITING_FOR_RESPONSE → SENDING → COMPLETED
 *                               ↘ REJECTED
 *                    (any state) → FAILED
 *
 * ConnectivityService registers a SendFileActionListener to receive the send request
 * and run the actual network I/O on a background thread — keeping the ViewModel
 * and Repository free of any transport knowledge.
 */
public class SendFileRepository {

    private static SendFileRepository instance;
    private static final String TAG = "SendFileRepository";

    // Current lifecycle status of the outgoing transfer
    private final MutableLiveData<SendFileStatus> sendStatus =
            new MutableLiveData<>(SendFileStatus.IDLE);

    // Display name of the file being sent (null when no transfer is active)
    private final MutableLiveData<String> currentFileName = new MutableLiveData<>(null);

    // Registered by ConnectivityService — bridges the UI send request to network operations
    private SendFileActionListener actionListener;

    /**
     * Callback interface implemented by ConnectivityService.
     * Keeps the ViewModel and Repository free of TransportManager knowledge.
     */
    public interface SendFileActionListener {
        /**
         * User chose a file to share — begin the send protocol on a background thread.
         *
         * @param uri      Content URI of the file to send (from the share Intent)
         */
        void onSendRequested(Uri uri);
    }

    private SendFileRepository() {}

    public static synchronized SendFileRepository getInstance() {
        if (instance == null) {
            instance = new SendFileRepository();
        }
        return instance;
    }

    /**
     * Registered by ConnectivityService once the transport is ready.
     */
    public void setActionListener(SendFileActionListener listener) {
        this.actionListener = listener;
    }

    // ============ Observers (for ViewModel) ============

    public LiveData<SendFileStatus> getSendStatus() {
        return sendStatus;
    }

    public LiveData<String> getCurrentFileName() {
        return currentFileName;
    }

    // ============ UI → Repository (called by ViewModel) ============

    /**
     * Called by SendFileViewModel when the user shares a file.
     * Fires the ActionListener so ConnectivityService can start the send protocol
     * on a background thread.
     *
     * IDLE → WAITING_FOR_RESPONSE
     *
     * @param uri     Content URI of the file chosen by the user.
     * @param fileName Display name shown in the UI while waiting.
     */
    public void requestSend(Uri uri, String fileName) {
        Log.d(TAG, "Send requested: " + fileName);
        currentFileName.postValue(fileName);
        sendStatus.postValue(SendFileStatus.WAITING_FOR_RESPONSE);

        if (actionListener != null) {
            actionListener.onSendRequested(uri);
        } else {
            Log.w(TAG, "No SendFileActionListener registered — is ConnectivityService running?");
            sendStatus.postValue(SendFileStatus.FAILED);
        }
    }

    // ============ State Transitions (called by SendFileUseCase) ============

    /**
     * Called by SendFileUseCase when the PC accepted and bytes are being streamed.
     * WAITING_FOR_RESPONSE → SENDING
     */
    public void onSendStarted() {
        Log.d(TAG, "PC accepted — streaming bytes for: " + currentFileName.getValue());
        sendStatus.postValue(SendFileStatus.SENDING);
    }

    /**
     * Called by SendFileUseCase when all bytes have been sent successfully.
     * SENDING → COMPLETED
     */
    public void onSendCompleted() {
        Log.d(TAG, "Send completed: " + currentFileName.getValue());
        sendStatus.postValue(SendFileStatus.COMPLETED);
    }

    /**
     * Called by SendFileUseCase when the PC user rejected the transfer.
     * WAITING_FOR_RESPONSE → REJECTED
     */
    public void onSendRejected() {
        Log.d(TAG, "Send rejected by PC for: " + currentFileName.getValue());
        currentFileName.postValue(null);
        sendStatus.postValue(SendFileStatus.REJECTED);
    }

    /**
     * Called by SendFileUseCase on any network error, timeout, or I/O failure.
     * (any state) → FAILED
     */
    public void onSendFailed() {
        Log.e(TAG, "Send failed for: " + currentFileName.getValue());
        currentFileName.postValue(null);
        sendStatus.postValue(SendFileStatus.FAILED);
    }

    /**
     * Resets to IDLE after the UI has acknowledged the terminal state
     * (COMPLETED / REJECTED / FAILED). Ready for the next transfer.
     */
    public void reset() {
        currentFileName.postValue(null);
        sendStatus.postValue(SendFileStatus.IDLE);
    }
}

package com.example.android.domain.usecases;

import android.util.Log;

import com.example.android.enums.FileTransferChannels;
import com.example.android.enums.FileTransferResponse;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.ReceiveFileRepository;

/**
 * Sends the user's Accept or Reject decision back to the PC via the response channel.
 *
 * Called by ConnectivityService on a background thread — this UseCase is synchronous
 * and must NOT be called on the main thread (network I/O).
 *
 * ConnectivityService wires this UseCase as the FileTransferActionListener on the
 * Repository, so the call chain is:
 *
 *   User taps Accept/Reject
 *   → FileTransferViewModel → Repository.onTransferAccepted/Rejected()
 *   → Repository fires ActionListener callback
 *   → ConnectivityService handles callback on background thread
 *   → calls this UseCase (synchronous)
 */
public class RespondToFileTransferUseCase {

    private static final String TAG = "RespondFileTransferUC";

    private final TransportManager transportManager;

    public RespondToFileTransferUseCase(TransportManager transportManager) {
        this.transportManager = transportManager;
    }

    /**
     * Sends ACCEPTED_FROM_ANDROID to the PC.
     * Call on a background thread. After this returns, the PC will open
     * the data channel and start streaming bytes.
     */
    public void accept() throws Exception {
        Log.d(TAG, "Sending ACCEPT to PC");
        transportManager.writeToChannel(
                FileTransferChannels.REGULAR_FILE_RESPONSE_FROM_ANDROID.getValue(),
                FileTransferResponse.ACCEPTED_FROM_ANDROID.getValue()
        );
    }

    /**
     * Sends REJECTED_FROM_ANDROID to the PC.
     * Call on a background thread. After this returns, the PC will abort.
     */
    public void reject() throws Exception {
        Log.d(TAG, "Sending REJECT to PC");
        transportManager.writeToChannel(
                FileTransferChannels.REGULAR_FILE_RESPONSE_FROM_ANDROID.getValue(),
                FileTransferResponse.REJECTED_FROM_ANDROID.getValue()
        );
    }
}

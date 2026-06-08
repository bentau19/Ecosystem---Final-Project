package com.example.android.services;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import com.example.android.repositories.ReceiveFileRepository;

/**
 * Handles Accept / Reject actions from the file transfer heads-up notification.
 *
 * When the app is in the background and a file transfer arrives, a notification
 * is shown with two action buttons. Tapping either button fires a broadcast
 * that this receiver handles — directly on the Repository Singleton.
 *
 * Note: We call the Repository directly here (not via ViewModel) because
 * BroadcastReceivers have no lifecycle and cannot hold a ViewModel reference.
 * The Repository Singleton is the correct entry point in this context.
 */
public class FileTransferActionReceiver extends BroadcastReceiver {

    private static final String TAG = "FileTransferReceiver";

    public static final String ACTION_ACCEPT = "com.example.android.FILE_TRANSFER_ACCEPT";
    public static final String ACTION_REJECT = "com.example.android.FILE_TRANSFER_REJECT";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || intent.getAction() == null) return;

        String action = intent.getAction();
        Log.d(TAG, "Received action: " + action);

        ReceiveFileRepository repository = ReceiveFileRepository.getInstance();

        switch (action) {
            case ACTION_ACCEPT:
                Log.d(TAG, "User accepted transfer from notification");
                repository.onTransferAccepted();
                break;
            case ACTION_REJECT:
                Log.d(TAG, "User rejected transfer from notification");
                repository.onTransferRejected();
                break;
            default:
                Log.w(TAG, "Unknown action: " + action);
        }
    }
}

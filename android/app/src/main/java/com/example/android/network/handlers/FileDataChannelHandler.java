package com.example.android.network.handlers;

import android.util.Log;

import com.example.android.domain.entities.ReceiveFileRequest;
import com.example.android.domain.usecases.ReceiveFileUseCase;
import com.example.android.enums.FileTransferChannels;
import com.example.android.repositories.ReceiveFileRepository;

/**
 * Handles the incoming file data channel (file_data_pc) from the PC.
 *
 * Triggered by the polling loop when the PC has opened the file_data_pc channel —
 * which only happens after the user has already sent ACCEPT via RespondToFileTransferUseCase.
 *
 * This handler exists specifically to eliminate the simultaneous-connect race condition:
 * the old flow had both Android and Desktop call connect("file_data_pc") at the same time,
 * causing TauSync's resolveConnectRaceAsync to create orphaned zombie connections.
 *
 * New flow:
 *   1. User taps Accept → Android sends ACCEPT → Android stops and waits.
 *   2. Desktop receives ACCEPT → Desktop calls connect("file_data_pc") alone.
 *   3. Polling loop (every 2 s) sees "file_data_pc" in getPeerWaitingWords().
 *   4. This handler's onPeerRequest() is called → Android connects and receives bytes.
 *
 * No race. No zombie. Desktop is always the sole initiator of file_data_pc.
 */
public class FileDataChannelHandler implements ChannelHandler {

    private static final String TAG = "FileDataHandler";

    private final ReceiveFileUseCase receiveFileUseCase;
    private final ReceiveFileRepository repository;

    public FileDataChannelHandler(ReceiveFileUseCase receiveFileUseCase,
                                  ReceiveFileRepository repository) {
        this.receiveFileUseCase = receiveFileUseCase;
        this.repository = repository;
    }

    @Override
    public String getChannelName() {
        return FileTransferChannels.REGULAR_FILE_DATA_PC_TO_ANDROID.getValue();
    }

    /**
     * Called by the polling loop when the PC has opened file_data_pc.
     * Runs on PeerRequestHandlerThread — safe to block for I/O.
     */
    @Override
    public void onPeerRequest() {
        Log.d("TauSyncFlow", "[FileTransfer] FileDataChannelHandler.onPeerRequest() called");

        ReceiveFileRequest request = repository.getPendingRequest().getValue();
        if (request == null) {
            Log.w(TAG, "No pending file transfer request — ignoring file_data_pc signal");
            return;
        }

        String fileName = request.fileName();
        Log.d(TAG, "Starting file receive for: " + fileName);

        // Blocks until all bytes are received and saved to Downloads.
        receiveFileUseCase.execute(fileName);
    }

    @Override
    public void onShutdown() {
        Log.d(TAG, "FileDataChannelHandler shut down");
    }
}

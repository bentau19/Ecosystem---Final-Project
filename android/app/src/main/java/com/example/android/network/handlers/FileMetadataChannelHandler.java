package com.example.android.network.handlers;

import android.util.Log;

import com.example.android.domain.entities.FileTransferRequest;
import com.example.android.enums.FileTransferChannels;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.FileTransferRepository;

import org.json.JSONObject;

/**
 * Handles incoming file transfer metadata from the PC (PC → Android flow).
 *
 * Responsibilities:
 * 1. Read the JSON metadata from the file_meta_pc channel
 * 2. Parse filename and size from the wire format: {"file_name": "...", "file_size": ...}
 * 3. Push the parsed request into FileTransferRepository → LiveData → ViewModel → UI
 *
 * What this handler does NOT do:
 * - Does not decide to accept or reject (that's the user's job via the UI)
 * - Does not read file bytes (that's ReceiveFileUseCase's job)
 * - Does not know about dialogs, notifications, or any Android UI components
 *
 * Wire format (defined by desktop FileMetadataSerializer):
 *   {"file_name": <string>, "file_size": <int>}
 */
public class FileMetadataChannelHandler implements ChannelHandler {

    private static final String TAG = "FileMetadataHandler";

    private static final String KEY_FILE_NAME = "file_name";
    private static final String KEY_FILE_SIZE = "file_size";

    private final TransportManager transportManager;
    private final FileTransferRepository repository;

    public FileMetadataChannelHandler(TransportManager transportManager,
                                      FileTransferRepository repository) {
        this.transportManager = transportManager;
        this.repository = repository;
    }

    @Override
    public String getChannelName() {
        return FileTransferChannels.REGULAR_FILE_METADATA_PC_TO_ANDROID.getValue();
    }

    @Override
    public void onPeerRequest() {
        try {
            String raw = transportManager.readFromChannel(
                    FileTransferChannels.REGULAR_FILE_METADATA_PC_TO_ANDROID.getValue()
            );

            Log.d(TAG, "Raw metadata received: " + raw);

            if (raw == null || raw.isEmpty()) {
                Log.w(TAG, "Empty metadata payload — ignoring");
                return;
            }

            JSONObject json = new JSONObject(raw);
            String fileName = json.getString(KEY_FILE_NAME);
            long fileSize = json.getLong(KEY_FILE_SIZE);

            if (fileName.isEmpty()) {
                Log.w(TAG, "Received empty file name — ignoring");
                return;
            }

            FileTransferRequest request = new FileTransferRequest(fileName, fileSize);
            Log.d(TAG, "Parsed request: " + fileName + " (" + request.getFormattedSize() + ")");

            // Hand off to the Repository — LiveData will notify ViewModel → UI
            repository.onTransferRequested(request);

        } catch (Exception e) {
            Log.e(TAG, "Failed to parse file metadata: " + e.getMessage());
            repository.onTransferFailed();
        }
    }

    @Override
    public void onShutdown() {
        Log.d(TAG, "FileMetadataChannelHandler shut down");
    }
}

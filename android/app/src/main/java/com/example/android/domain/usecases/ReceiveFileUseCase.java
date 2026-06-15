package com.example.android.domain.usecases;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Log;

import com.example.android.R;
import com.example.android.enums.FileTransferChannels;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.ReceiveFileRepository;

import java.io.IOException;
import java.io.OutputStream;

/**
 * Receives file bytes from the PC and saves them to the public Downloads folder.
 *
 * Called after the user accepts the transfer (Repository status = RECEIVING).
 * Uses MediaStore API for Android 10+ compatibility — no storage permissions needed.
 *
 * Flow:
 *   User accepted → Repository status = RECEIVING
 *   → ConnectivityService calls this UseCase on a background thread
 *   → reads raw bytes from file_data_pc channel
 *   → saves to Downloads via MediaStore
 *   → updates Repository: COMPLETED or FAILED
 */
public class ReceiveFileUseCase {

    private static final String TAG = "ReceiveFileUseCase";

    private final TransportManager transportManager;
    private final ReceiveFileRepository repository;
    private final Context context;

    public ReceiveFileUseCase(TransportManager transportManager,
                              ReceiveFileRepository repository,
                              Context context) {
        this.transportManager = transportManager;
        this.repository = repository;
        this.context = context.getApplicationContext();
    }

    /**
     * Streams file bytes from the data channel directly into the Downloads folder.
     * Must be called from a background thread — blocks until all bytes are received.
     *
     * Uses a 64 KB pipe buffer: bytes flow TauSync → OutputStream without ever
     * holding the full file in RAM, so arbitrarily large files are supported.
     *
     * @param fileName The file name received in the metadata (e.g. "image.png")
     */
    public void execute(String fileName) {
        Log.d(TAG, "Starting file receive: " + fileName);
        Log.d("TauSyncFlow", "[FileTransfer] ReceiveFileUseCase.execute() started for: " + fileName);

        ContentResolver resolver = context.getContentResolver();
        Uri uri = null;

        try {
            // 1. Create the MediaStore entry up front so we can stream straight into it.
            ContentValues values = new ContentValues();
            values.put(MediaStore.Downloads.DISPLAY_NAME, fileName);
            values.put(MediaStore.Downloads.MIME_TYPE, guessMimeType(fileName));
            values.put(MediaStore.Downloads.IS_PENDING, 1);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS+ "/" + context.getString(R.string.app_name));
            }

            uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (uri == null) {
                throw new IOException("MediaStore failed to create entry for: " + fileName);
            }

            // 2. Open the MediaStore OutputStream and pipe TauSync bytes directly into it.
            //    transportManager.streamChannelToOutputStream reads in 64 KB chunks until
            //    the desktop closes the channel (FIN) — no full-file buffering in RAM.
            try (OutputStream out = resolver.openOutputStream(uri)) {
                if (out == null) {
                    throw new IOException("Failed to open MediaStore output stream for: " + fileName);
                }
                transportManager.streamChannelToOutputStream(
                        FileTransferChannels.REGULAR_FILE_DATA_PC_TO_ANDROID.getValue(),
                        out
                );
            }

            // 3. Publish the file — makes it visible to other apps (Files, Gallery, etc.)
            values.clear();
            values.put(MediaStore.Downloads.IS_PENDING, 0);
            resolver.update(uri, values, null, null);

            repository.onTransferCompleted();
            Log.d(TAG, "File saved to Downloads: " + fileName);
            Log.d("TauSyncFlow", "[FileTransfer] ReceiveFileUseCase COMPLETED: " + fileName);

        } catch (Exception e) {
            Log.e(TAG, "Error receiving file: " + e.getMessage());
            Log.e("TauSyncFlow", "[FileTransfer] ReceiveFileUseCase FAILED: " + e.getMessage());

            // Clean up the incomplete MediaStore entry so it doesn't appear as a corrupt file.
            if (uri != null) {
                try { resolver.delete(uri, null, null); } catch (Exception ignored) {}
            }

            repository.onTransferFailed();
        }
    }

    /**
     * Guesses MIME type from file extension.
     * Falls back to generic binary stream if unknown.
     */
    private String guessMimeType(String fileName) {
        if (fileName == null || !fileName.contains(".")) {
            return "application/octet-stream";
        }
        String ext = fileName.substring(fileName.lastIndexOf('.') + 1).toLowerCase();
        switch (ext) {
            case "jpg":
            case "jpeg": return "image/jpeg";
            case "png":  return "image/png";
            case "gif":  return "image/gif";
            case "mp4":  return "video/mp4";
            case "mp3":  return "audio/mpeg";
            case "pdf":  return "application/pdf";
            case "txt":  return "text/plain";
            case "zip":  return "application/zip";
            default:     return "application/octet-stream";
        }
    }
}

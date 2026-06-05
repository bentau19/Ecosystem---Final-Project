package com.example.android.domain.usecases;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Log;

import com.example.android.enums.FileTransferChannels;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.FileTransferRepository;

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
    private final FileTransferRepository repository;
    private final Context context;

    public ReceiveFileUseCase(TransportManager transportManager,
                              FileTransferRepository repository,
                              Context context) {
        this.transportManager = transportManager;
        this.repository = repository;
        this.context = context.getApplicationContext();
    }

    /**
     * Reads all file bytes from the data channel and saves the file to Downloads.
     * Must be called from a background thread — blocks until all bytes are received.
     *
     * @param fileName The file name received in the metadata (e.g. "image.png")
     */
    public void execute(String fileName) {
        Log.d(TAG, "Starting file receive: " + fileName);

        try {
            // 1. Read all bytes from the data channel
            byte[] fileBytes = transportManager.readBytesFromChannel(
                    FileTransferChannels.REGULAR_FILE_DATA_PC_TO_ANDROID.getValue()
            );

            if (fileBytes == null || fileBytes.length == 0) {
                Log.e(TAG, "Received empty file data");
                repository.onTransferFailed();
                return;
            }

            Log.d(TAG, "Received " + fileBytes.length + " bytes for: " + fileName);

            // 2. Save to Downloads using MediaStore API (works on Android 10+, no permissions needed)
            saveToDownloads(fileName, fileBytes);

            repository.onTransferCompleted();
            Log.d(TAG, "File saved successfully: " + fileName);

        } catch (Exception e) {
            Log.e(TAG, "Error receiving file: " + e.getMessage());
            repository.onTransferFailed();
        }
    }

    /**
     * Saves raw bytes to the public Downloads folder using MediaStore.
     * Compatible with Android 10+ (API 29+) — no WRITE_EXTERNAL_STORAGE permission needed.
     */
    private void saveToDownloads(String fileName, byte[] bytes) throws IOException {
        ContentValues values = new ContentValues();
        values.put(MediaStore.Downloads.DISPLAY_NAME, fileName);
        values.put(MediaStore.Downloads.MIME_TYPE, guessMimeType(fileName));
        values.put(MediaStore.Downloads.IS_PENDING, 1);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
        }

        ContentResolver resolver = context.getContentResolver();
        Uri uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);

        if (uri == null) {
            throw new IOException("MediaStore failed to create URI for: " + fileName);
        }

        try (OutputStream out = resolver.openOutputStream(uri)) {
            if (out == null) {
                throw new IOException("Failed to open output stream for: " + fileName);
            }
            out.write(bytes);
            out.flush();
        }

        // Mark file as complete — makes it visible to other apps
        values.clear();
        values.put(MediaStore.Downloads.IS_PENDING, 0);
        resolver.update(uri, values, null, null);

        Log.d(TAG, "Saved to Downloads: " + fileName + " (" + bytes.length + " bytes)");
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

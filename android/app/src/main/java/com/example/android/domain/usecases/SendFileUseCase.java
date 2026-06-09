package com.example.android.domain.usecases;

import android.content.ContentResolver;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.util.Log;

import com.example.android.enums.FileTransferChannels;
import com.example.android.enums.FileTransferResponse;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.SendFileRepository;

import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Sends a file from Android to the connected PC.
 *
 * Must be called from a background thread — all operations are synchronous network I/O.
 *
 * Protocol (Android → PC):
 *   1. Resolve filename + size from URI via ContentResolver (Cursor closed via try-with-resources).
 *   2. Send JSON metadata to PC over REGULAR_FILE_METADATA_ANDROID_TO_PC.
 *   3. Wait up to RESPONSE_TIMEOUT_SECONDS for PC's Accept / Reject on REGULAR_FILE_RESPONSE_FROM_PC.
 *      Timeout → FAILED with a clear "request timed out" message.
 *   4. If accepted: stream raw bytes to REGULAR_FILE_DATA_ANDROID_TO_PC in 64 KB chunks.
 *   5. Update SendFileRepository: COMPLETED / REJECTED / FAILED.
 *
 * JSON wire format (matches desktop FileMetadataSerializer):
 *   {"file_name": "photo.jpg", "file_size": 4194304, "modified_at": 1700000000000}
 */
public class SendFileUseCase {

    private static final String TAG = "SendFileUseCase";

    /**
     * Seconds to wait for the PC user's Accept / Reject decision before giving up.
     * If the user walks away from the PC without responding, the transfer is cancelled
     * after this timeout and the status becomes FAILED.
     */
    private static final int RESPONSE_TIMEOUT_SECONDS = 123;

    private final TransportManager transportManager;
    private final SendFileRepository repository;
    private final Context context;

    public SendFileUseCase(TransportManager transportManager,
                           SendFileRepository repository,
                           Context context) {
        this.transportManager = transportManager;
        this.repository = repository;
        this.context = context.getApplicationContext();
    }

    /**
     * Executes the full send protocol for the given file URI.
     * Must be called from a background thread.
     *
     * @param uri Content URI of the file to send (from the share Intent's EXTRA_STREAM).
     */
    public void execute(Uri uri) {
        try {
            ContentResolver resolver = context.getContentResolver();

            // ── Step 1: Resolve filename + size ──────────────────────────────────
            // Cursor MUST be closed after use — try-with-resources guarantees this
            // even if an exception is thrown mid-cursor, preventing memory leaks.
            String fileName;
            long fileSize;
            long fileModifiedAt; // Unix epoch ms; 0 = not available

            try (Cursor cursor = resolver.query(uri, null, null, null, null)) {
                if (cursor == null || !cursor.moveToFirst()) {
                    throw new IOException("Cannot read file metadata from URI: " + uri);
                }

                int nameIndex         = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                int sizeIndex         = cursor.getColumnIndex(OpenableColumns.SIZE);
                // DATE_MODIFIED is in seconds since epoch — multiply by 1000 for ms wire format.
                int dateModifiedIndex = cursor.getColumnIndex(MediaStore.MediaColumns.DATE_MODIFIED);

                fileName       = (nameIndex >= 0) ? cursor.getString(nameIndex) : null;
                fileSize       = (sizeIndex >= 0) ? cursor.getLong(sizeIndex) : -1L;
                fileModifiedAt = (dateModifiedIndex >= 0 && !cursor.isNull(dateModifiedIndex))
                        ? cursor.getLong(dateModifiedIndex) * 1000L
                        : 0L;
            }

            if (fileName == null || fileName.isEmpty()) {
                throw new IOException("Could not determine file name from URI: " + uri);
            }
            if (fileSize < 0) {
                throw new IOException("Could not determine file size for: " + fileName);
            }

            Log.d(TAG, "Resolved file — name: " + fileName + ", size: " + fileSize + " bytes");

            // ── Step 2: Build JSON metadata ───────────────────────────────────────
            // Wire format matches desktop's FileMetadataSerializer:
            //   {"file_name": "photo.jpg", "file_size": 4194304}
            JSONObject json = new JSONObject();
            json.put("file_name", fileName);
            json.put("file_size", fileSize);
            json.put("modified_at", fileModifiedAt);
            String metadataPayload = json.toString();

            // ── Step 3: Send metadata to PC ───────────────────────────────────────
            Log.d(TAG, "Sending metadata: " + metadataPayload);
            transportManager.writeToChannel(
                    FileTransferChannels.REGULAR_FILE_METADATA_ANDROID_TO_PC.getValue(),
                    metadataPayload
            );

            // ── Step 4: Wait for PC's Accept / Reject with timeout ────────────────
            // readFromChannel blocks until the PC writes a response.
            // We wrap it in a Future so we can enforce a hard timeout:
            // if the PC user ignores the prompt for too long, we fail gracefully
            // instead of blocking forever.
            Log.d(TAG, "Waiting for PC response (timeout: " + RESPONSE_TIMEOUT_SECONDS + "s)");
            String response = readWithTimeout(
                    FileTransferChannels.REGULAR_FILE_RESPONSE_FROM_PC.getValue(),
                    RESPONSE_TIMEOUT_SECONDS
            );

            if (FileTransferResponse.REJECTED_FROM_PC.getValue().equals(response)) {
                Log.d(TAG, "PC rejected the file: " + fileName);
                repository.onSendRejected();
                return;
            }

            if (!FileTransferResponse.ACCEPTED_FROM_PC.getValue().equals(response)) {
                throw new IOException("Unexpected response token from PC: \"" + response + "\"");
            }

            // ── Step 5: PC accepted — stream bytes ────────────────────────────────
            Log.d(TAG, "PC accepted — streaming bytes for: " + fileName);
            repository.onSendStarted();

            try (InputStream inputStream = resolver.openInputStream(uri)) {
                if (inputStream == null) {
                    throw new IOException("Failed to open InputStream for URI: " + uri);
                }
                // Streams in 64 KB chunks — the full file is never held in RAM.
                transportManager.streamInputStreamToChannel(
                        FileTransferChannels.REGULAR_FILE_DATA_ANDROID_TO_PC.getValue(),
                        inputStream
                );
            }

            repository.onSendCompleted();
            Log.d(TAG, "File sent successfully: " + fileName);

        } catch (Exception e) {
            Log.e(TAG, "Send failed: " + e.getMessage());
            repository.onSendFailed();
        }
    }

    // ── Private helpers ───────────────────────────────────────────────────────────

    /**
     * Reads a string from {@code channel} with a hard timeout.
     *
     * Runs the blocking {@link TransportManager#readFromChannel} call on a
     * dedicated thread and waits at most {@code timeoutSeconds} for a result.
     * If the deadline is exceeded the thread is interrupted and a descriptive
     * Exception is thrown so the caller can transition the repository to FAILED.
     *
     * @param channel        TauSync channel to read from.
     * @param timeoutSeconds Maximum seconds to wait before giving up.
     * @return The string value read from the channel.
     * @throws Exception on read failure or timeout.
     */
    private String readWithTimeout(String channel, int timeoutSeconds) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        Future<String> future = executor.submit(() ->
                transportManager.readFromChannel(channel)
        );
        try {
            return future.get(timeoutSeconds, TimeUnit.SECONDS);
        } catch (TimeoutException e) {
            future.cancel(true);
            throw new Exception(
                    "PC did not respond within " + timeoutSeconds + " seconds — request timed out"
            );
        } finally {
            // Always shut down the executor to release the thread,
            // whether we got a result, timed out, or encountered another error.
            executor.shutdownNow();
        }
    }
}

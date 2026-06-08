package com.example.android.ui;

import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.util.Log;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.repositories.DeviceRepository;
import com.example.android.services.ConnectivityService;

/**
 * Invisible trampoline Activity for the Android share sheet (ACTION_SEND).
 *
 * This is NOT part of the app's Single Activity Architecture — it has no UI,
 * no Fragments, and the user is never aware of it. It acts purely as a
 * system hook (similar in role to a BroadcastReceiver) that Android requires
 * to be an Activity in order to appear in the share sheet.
 *
 * Flow: share sheet tap → this Activity starts → resolves file → delegates to
 * SendFileViewModel → SendFileRepository → finish(). The progress notification is driven by
 * ConnectivityService observing SendFileRepository, so MainActivity is never
 * brought to the foreground.
 */
public class ShareReceiverActivity extends AppCompatActivity {

    private static final String TAG = "ShareReceiverActivity";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        handleShareIntent(getIntent());
        finish();
    }

    private void handleShareIntent(Intent intent) {
        if (intent == null || !Intent.ACTION_SEND.equals(intent.getAction())) return;

        Uri fileUri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
        if (fileUri == null) {
            Toast.makeText(this, "No file found in share request.", Toast.LENGTH_SHORT).show();
            return;
        }

        ConnectionStatus status = DeviceRepository.getInstance().getConnectionStatus().getValue();
        if (status != ConnectionStatus.CONNECTED) {
            Toast.makeText(this, "Not connected to PC — connect first.", Toast.LENGTH_LONG).show();
            return;
        }

        // Resolve the file name while the Activity is alive and the URI grant is valid.
        String fileName = resolveFileName(fileUri);

        // Delegate the URI grant to ConnectivityService via a single Intent that both
        // transfers ownership of the share-sheet permission AND carries the send request.
        // FLAG_GRANT_READ_URI_PERMISSION tells Android to register an independent grant
        // for the service — one that is tied to the service's lifecycle, not this
        // Activity's task. ConnectivityService.onStartCommand() receives the Intent
        // *after* the grant is registered and triggers the send flow from there,
        // guaranteeing the grant is fully active before any ContentResolver I/O runs.
        Intent sendIntent = new Intent(this, ConnectivityService.class);
        sendIntent.setAction("com.example.android.ACTION_GRANT_FILE_URI");
        sendIntent.setData(fileUri);
        sendIntent.putExtra("FILE_NAME", fileName);
        sendIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        startService(sendIntent);
    }

    private String resolveFileName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(uri, null, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (nameIndex >= 0) {
                    String name = cursor.getString(nameIndex);
                    if (name != null && !name.isEmpty()) return name;
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "Could not resolve file name: " + e.getMessage());
        }
        String lastSegment = uri.getLastPathSegment();
        return (lastSegment != null) ? lastSegment : "file";
    }
}

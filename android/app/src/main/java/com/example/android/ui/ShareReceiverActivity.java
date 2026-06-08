package com.example.android.ui;

import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.util.Log;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.repositories.DeviceRepository;
import com.example.android.viewmodel.SendFileViewModel;

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

        String fileName = resolveFileName(fileUri);
        new ViewModelProvider(this).get(SendFileViewModel.class).sendFile(fileUri, fileName);
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

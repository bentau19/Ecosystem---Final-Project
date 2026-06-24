package com.example.android.domain.usecases;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.util.Log;

import com.example.android.enums.ClipboardChannels;
import com.example.android.network.transport.TransportManager;

import org.json.JSONObject;

/**
 * Reads the current clipboard content and sends it to the connected PC.
 *
 * <p>Must be called from a background thread — {@link TransportManager#writeToChannel}
 * performs synchronous network I/O.
 *
 * <p>Wire format (matches desktop ClipboardService):
 * <pre>{"type": "text", "content": "..."}</pre>
 *
 * <p>Future extension: add {@code "type": "image"} branch once image support is needed.
 */
public class ClipboardSyncUseCase {

    private static final String TAG = "ClipboardSyncUseCase";

    private final TransportManager transportManager;
    private final Context context;

    public ClipboardSyncUseCase(TransportManager transportManager, Context context) {
        this.transportManager = transportManager;
        this.context = context.getApplicationContext();
    }

    /**
     * Reads the clipboard and sends its text content to the PC.
     * Must be called from a background thread.
     */
    public void execute() {
        try {
            ClipboardManager clipboardManager =
                    (ClipboardManager) context.getSystemService(Context.CLIPBOARD_SERVICE);

            if (clipboardManager == null || !clipboardManager.hasPrimaryClip()) {
                Log.w(TAG, "Clipboard is empty — nothing to send");
                return;
            }

            ClipData clipData = clipboardManager.getPrimaryClip();
            if (clipData == null || clipData.getItemCount() == 0) {
                Log.w(TAG, "Clipboard has no items");
                return;
            }

            CharSequence text = clipData.getItemAt(0).getText();
            if (text == null) {
                Log.w(TAG, "Clipboard item has no text — may be an image or file reference");
                return;
            }

            // Build JSON payload — extensible for future "image" type
            JSONObject payload = new JSONObject();
            payload.put("type", "text");
            payload.put("content", text.toString());

            Log.d(TAG, "Sending clipboard to PC: " + text.length() + " chars");
            transportManager.writeToChannel(
                    ClipboardChannels.CLIPBOARD_ANDROID_TO_PC.getValue(),
                    payload.toString()
            );
            Log.d(TAG, "Clipboard sent successfully");

        } catch (Exception e) {
            Log.e(TAG, "Failed to send clipboard: " + e.getMessage());
        }
    }
}

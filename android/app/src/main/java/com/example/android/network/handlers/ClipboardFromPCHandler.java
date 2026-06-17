package com.example.android.network.handlers;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.util.Log;

import com.example.android.enums.ClipboardChannels;
import com.example.android.network.transport.TransportManager;

import org.json.JSONObject;

/**
 * Handles incoming clipboard content from the PC (clipboard_pc_to_android channel).
 *
 * <p>Triggered by the polling loop when the PC has opened the
 * {@code clipboard_pc_to_android} channel — which happens automatically every
 * time the PC clipboard changes (driven by QClipboard.dataChanged on the Desktop).
 *
 * <p>Wire format (matches desktop ClipboardService._send_to_android):
 * <pre>{"type": "text", "content": "..."}</pre>
 *
 * <p>Writing to ClipboardManager is always permitted on Android — unlike reading,
 * which is blocked for background apps on Android 10+.  This handler therefore
 * works correctly even when the app is in the background.
 */
public class ClipboardFromPCHandler implements ChannelHandler {

    private static final String TAG = "ClipboardFromPCHandler";

    private final TransportManager transportManager;
    private final Context context;

    public ClipboardFromPCHandler(TransportManager transportManager, Context context) {
        this.transportManager = transportManager;
        this.context = context.getApplicationContext();
    }

    @Override
    public String getChannelName() {
        return ClipboardChannels.CLIPBOARD_PC_TO_ANDROID.getValue();
    }

    /**
     * Called by the polling loop when the PC has opened clipboard_pc_to_android.
     * Runs on PeerRequestHandlerThread — safe to block for I/O.
     */
    @Override
    public void onPeerRequest() {
        try {
            String raw = transportManager.readFromChannel(
                    ClipboardChannels.CLIPBOARD_PC_TO_ANDROID.getValue()
            );

            JSONObject payload = new JSONObject(raw);
            String type = payload.optString("type", "");

            if (!"text".equals(type)) {
                Log.w(TAG, "Unsupported clipboard type from PC: " + type);
                return;
            }

            String content = payload.optString("content", "");
            if (content.isEmpty()) {
                Log.w(TAG, "Empty clipboard content from PC — ignoring");
                return;
            }

            ClipboardManager cm =
                    (ClipboardManager) context.getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm == null) {
                Log.e(TAG, "ClipboardManager unavailable");
                return;
            }

            cm.setPrimaryClip(ClipData.newPlainText("SyncDose", content));
            Log.d(TAG, "Clipboard set from PC: " + content.length() + " chars");

        } catch (Exception e) {
            Log.e(TAG, "Failed to receive clipboard from PC: " + e.getMessage());
        }
    }

    @Override
    public void onShutdown() {
        Log.d(TAG, "ClipboardFromPCHandler shut down");
    }
}

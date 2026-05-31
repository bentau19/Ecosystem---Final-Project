package com.example.android.utils;

import android.util.Log;

import com.example.tausync_lib.implementations.management.TauSyncStream;
import com.example.tausync_lib.sdk.TauSync;

import java.nio.charset.StandardCharsets;

/**
 * Android implementation of the TauSync network protocol.
 * Mirrored from the 'network' module in the desktop client.
 */
public class NetworkHandler {

    private static final String TAG = "NetworkHandler";

    /**
     * מקביל ל-write_to_channel ב-Python.
     */
    public static void writeToChannel(TauSync tau, String channel, String data) {
        if (tau == null || !tau.isConnected()) {
            Log.w(TAG, "Cannot write: TauSync is not connected.");
            return;
        }

        try (TauSyncStream stream = tau.connect(channel)) {
            if (stream != null) {
                // ה-SDK מטפל בכתיבת המחרוזת. אם אין flush, הסגירה של ה-try (ה-close) תשלח את הנתונים.
                stream.writeString(data);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error writing to channel " + channel + ": " + e.getMessage());
        }
    }

    /**
     * מקביל ל-read_from_channel ב-Python.
     */
    public static String readFromChannel(TauSync tau, String channel) {
        if (tau == null || !tau.isConnected()) return "";

        try (TauSyncStream stream = tau.connect(channel)) {
            if (stream != null) {
                // המרה מ-byte[] ל-String תוך שימוש ב-UTF-8 כדי להתאים לפייתון.
                byte[] data = stream.readAll();
                return new String(data, StandardCharsets.UTF_8);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error reading from channel " + channel + ": " + e.getMessage());
        }
        return "";
    }
}
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
     * Corresponds to write_to_channel in Python.
     * @param tau TauSync instance.
     * @param channel Channel name.
     * @param data Data to write.
     */
    public static void writeToChannel(TauSync tau, String channel, String data) {
        if (tau == null || !tau.isConnected()) {
            Log.w(TAG, "Cannot write: TauSync is not connected.");
            return;
        }

        try (TauSyncStream stream = tau.connect(channel)) {
            if (stream != null) {
                // The SDK handles string writing. If no flush is called, 
                // closing the stream in the try-with-resources block will send the data.
                stream.writeString(data);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error writing to channel " + channel + ": " + e.getMessage());
        }
    }

    /**
     * Corresponds to read_from_channel in Python.
     * @param tau TauSync instance.
     * @param channel Channel name.
     * @return Data read from the channel.
     */
    public static String readFromChannel(TauSync tau, String channel) {
        if (tau == null || !tau.isConnected()) return "";

        try (TauSyncStream stream = tau.connect(channel)) {
            if (stream != null) {
                // Convert byte[] to String using UTF-8 to match Python's encoding.
                byte[] data = stream.readAll();
                return new String(data, StandardCharsets.UTF_8);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error reading from channel " + channel + ": " + e.getMessage());
        }
        return "";
    }

    /**
     * Reads raw bytes from a channel.
     * Used for binary data (file contents) where String conversion would corrupt the data.
     *
     * @param tau TauSync instance.
     * @param channel Channel name.
     * @return Raw byte array from the channel, or empty array on failure.
     */
    public static byte[] readBytesFromChannel(TauSync tau, String channel) {
        if (tau == null || !tau.isConnected()) return new byte[0];

        try (TauSyncStream stream = tau.connect(channel)) {
            if (stream != null) {
                return stream.readAll();
            }
        } catch (Exception e) {
            Log.e(TAG, "Error reading bytes from channel " + channel + ": " + e.getMessage());
        }
        return new byte[0];
    }
}

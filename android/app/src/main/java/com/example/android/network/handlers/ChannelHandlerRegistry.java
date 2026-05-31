package com.example.android.network.handlers;

import android.util.Log;
import java.util.HashMap;
import java.util.Map;

/**
 * ChannelHandlerRegistry manages all channel handlers.
 *
 * This registry enables a plugin-like architecture where:
 * - New handlers can be registered without modifying ConnectivityService
 * - Handlers can be swapped/updated dynamically
 * - Future features are easy to add
 */
public class ChannelHandlerRegistry {

    private static final String TAG = "ChannelRegistry";
    private final Map<String, ChannelHandler> handlers = new HashMap<>();

    /**
     * Registers a handler for a specific channel.
     * If a handler for this channel already exists, it will be replaced.
     */
    public void registerHandler(String channel, ChannelHandler handler) {
        if (handler != null) {
            handlers.put(channel, handler);
            Log.d(TAG, "Handler registered for channel: " + channel);
        }
    }

    /**
     * Unregisters a handler for a specific channel.
     * Calls onShutdown() on the handler being removed.
     */
    public void unregisterHandler(String channel) {
        ChannelHandler handler = handlers.remove(channel);
        if (handler != null) {
            try {
                handler.onShutdown();
            } catch (Exception e) {
                Log.e(TAG, "Error shutting down handler for " + channel + ": " + e.getMessage());
            }
            Log.d(TAG, "Handler unregistered for channel: " + channel);
        }
    }

    /**
     * Gets a handler for a specific channel.
     */
    public ChannelHandler getHandler(String channel) {
        return handlers.get(channel);
    }

    /**
     * Processes a peer request by delegating to the appropriate handler.
     * If no handler is registered for the channel, logs a warning.
     */
    public void handlePeerRequest(String channel) {
        ChannelHandler handler = handlers.get(channel);
        if (handler != null) {
            try {
                handler.onPeerRequest();
            } catch (Exception e) {
                Log.e(TAG, "Error handling request for channel [" + channel + "]: " + e.getMessage());
            }
        } else {
            Log.w(TAG, "No handler registered for channel: " + channel);
        }
    }

    /**
     * Shuts down all registered handlers and clears the registry.
     * Called when the service is shutting down.
     */
    public void shutdownAll() {
        // 1. יוצרים עותק נפרד של המפתחות כדי לא לרוץ ישירות על המפה הפעילה
        java.util.List<String> channelKeys = new java.util.ArrayList<>(handlers.keySet());

        // 2. רצים על העותק הבטוח
        for (String channel : channelKeys) {
            ChannelHandler handler = handlers.get(channel);
            if (handler != null) {
                try {
                    handler.onShutdown();
                } catch (Exception e) {
                    android.util.Log.e("Registry", "Error shutting down handler for " + channel, e);
                }
            }
        }

        // 3. מנקים את המפה בבת אחת בסוף, בבטחה
        handlers.clear();
    }

    /**
     * Gets the number of registered handlers.
     */
    public int getHandlerCount() {
        return handlers.size();
    }
}


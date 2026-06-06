package com.example.android.network.handlers;

import android.util.Log;
import com.example.android.network.transport.TransportManager;

/**
 * Generic handler for device-info channels that only need to return a value.
 */
public class DeviceInfoChannelHandler implements ChannelHandler {

    public interface ValueProvider {
        String getValue() throws Exception;
    }

    private static final String TAG = "DeviceInfoHandler";
    private final String channel;
    private final TransportManager transportManager;
    private final ValueProvider valueProvider;

    public DeviceInfoChannelHandler(
            String channel,
            TransportManager transportManager,
            ValueProvider valueProvider
    ) {
        this.channel = channel;
        this.transportManager = transportManager;
        this.valueProvider = valueProvider;
    }

    @Override
    public String getChannelName() {
        return channel;
    }

    @Override
    public void onPeerRequest() {
        try {
            String value = valueProvider.getValue();
            transportManager.writeToChannel(channel, value != null ? value : "");
            Log.v(TAG, "Sent channel [" + channel + "]");
        } catch (Exception e) {
            Log.e(TAG, "Failed to handle channel [" + channel + "]: " + e.getMessage(), e);
        }
    }

    @Override
    public void onShutdown() {
        Log.d(TAG, "Handler shut down for channel [" + channel + "]");
    }
}

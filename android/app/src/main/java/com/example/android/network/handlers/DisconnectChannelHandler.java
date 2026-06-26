package com.example.android.network.handlers;

import android.util.Log;

import com.example.android.enums.SessionChannels;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.DeviceRepository;

/**
 * DisconnectChannelHandler handles disconnect requests initiated by the PC.
 *
 * When the PC requests a disconnect:
 * 1. Read the disconnect signal from the channel
 * 2. Clear the remote connection state in the repository
 * 3. Notify the transport manager to disconnect
 * 4. UI observers will be notified of the state change
 */
public class DisconnectChannelHandler implements ChannelHandler {

    private static final String TAG = "DisconnectHandler";
    private final DeviceRepository repository;
    private final TransportManager transportManager;
    private final Runnable onDisconnect;

    public DisconnectChannelHandler(DeviceRepository repository, TransportManager transportManager, Runnable onDisconnect) {
        this.repository = repository;
        this.transportManager = transportManager;
        this.onDisconnect = onDisconnect;
    }

    @Override
    public String getChannelName() {
        return SessionChannels.DISCONNECT_FROM_PC.getValue();
    }

    @Override
    public void onPeerRequest() {
        try {
            Log.d(TAG, "[Disconnect] Attempting to read disconnect signal from PC");

            String disconnectSignal = transportManager.readFromChannel(SessionChannels.DISCONNECT_FROM_PC.getValue());
            Log.d(TAG, "[Disconnect] Signal received from PC: '" + disconnectSignal + "'");

            // Mark PC-initiated disconnect so ConnectFragment.onResume skips auto-reconnect.
            repository.setJustDisconnectedByPc();

            // Stop the polling executor NOW — before the PC closes the TCP socket.
            // After this read the PC will immediately close the connection; the next
            // polling tick would throw → handlePollingFailure() sees status==CONNECTED
            // → attemptConnection() → spurious auto-reconnect.
            // prepareForDisconnect() sets status=DISCONNECTING and awaits any in-flight
            // tick (via awaitTermination) so handlePollingFailure() can no longer fire
            // with a stale CONNECTED status.
            transportManager.prepareForDisconnect();
            Log.d(TAG, "[Disconnect] Polling stopped, proceeding with cleanup");

            // Disconnect from the repository (sets RemotePC to null)
            repository.disconnect();
            Log.d(TAG, "[Disconnect] Repository disconnected - RemotePC set to null");

            // Trigger the transport disconnect via the callback
            if (onDisconnect != null) {
                Log.d(TAG, "[Disconnect] Calling onDisconnect callback to cleanup service");
                onDisconnect.run();
            } else {
                Log.w(TAG, "[Disconnect] onDisconnect callback is null!");
            }

        } catch (Exception e) {
            Log.e(TAG, "[Disconnect] Error handling disconnect request: " + e.getMessage());
            e.printStackTrace();
        }
    }

    @Override
    public void onShutdown() {
        Log.d(TAG, "Disconnect handler shut down");
    }
}

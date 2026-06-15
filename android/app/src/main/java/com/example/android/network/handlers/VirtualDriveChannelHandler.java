package com.example.android.network.handlers;

import android.util.Log;

import com.example.android.domain.usecases.VirtualDriveUseCase;
import com.example.android.enums.VirtualDriveChannels;

/**
 * {@link ChannelHandler} for one virtual-drive TauSync channel.
 *
 * <p>One instance of this class is registered per channel in
 * {@link com.example.android.services.ConnectivityService#registerChannelHandlers()}.
 * When the polling loop detects that the PC has a waiting request for a virtual-
 * drive channel, the registry calls {@link #onPeerRequest()} on the matching
 * instance, which dispatches to the appropriate {@link VirtualDriveUseCase} method.
 *
 * <p>All dispatched methods block briefly on the negotiation exchange (reading
 * the PC's JSON request + writing the ack) on {@code PeerRequestHandlerThread}.
 * Heavy data I/O (file reads/writes) is delegated to dedicated background threads
 * spawned inside the UseCase — this handler always returns promptly.
 *
 * <p>No persistent state is held here; {@link #onShutdown()} is a no-op.
 */
public class VirtualDriveChannelHandler implements ChannelHandler {

    private static final String TAG = "VDriveHandler";

    private final String channelName;
    private final VirtualDriveUseCase useCase;

    /**
     * @param channelName The exact TauSync meeting word this instance handles
     *                    (e.g. {@code "virtual_drive_list"}).
     * @param useCase     Shared {@link VirtualDriveUseCase} — thread-safe, may be
     *                    called concurrently from different handler instances.
     */
    public VirtualDriveChannelHandler(String channelName, VirtualDriveUseCase useCase) {
        this.channelName = channelName;
        this.useCase     = useCase;
    }

    @Override
    public String getChannelName() {
        return channelName;
    }

    /**
     * Dispatches to the correct {@link VirtualDriveUseCase} method based on
     * this instance's channel name.
     *
     * <p>Called by {@link com.example.android.network.handlers.ChannelHandlerRegistry}
     * on {@code PeerRequestHandlerThread}.  Any exception is caught and logged
     * so a single failing op never takes down the polling loop.
     */
    @Override
    public void onPeerRequest() {
        try {
            if (channelName.equals(VirtualDriveChannels.VIRTUAL_DRIVE_LIST.getValue())) {
                useCase.handleList();
            } else if (channelName.equals(VirtualDriveChannels.VIRTUAL_DRIVE_STAT.getValue())) {
                useCase.handleStat();
            } else if (channelName.equals(VirtualDriveChannels.VIRTUAL_DRIVE_READ.getValue())) {
                useCase.handleRead();
            } else if (channelName.equals(VirtualDriveChannels.VIRTUAL_DRIVE_WRITE.getValue())) {
                useCase.handleWrite();
            } else if (channelName.equals(VirtualDriveChannels.VIRTUAL_DRIVE_CREATE.getValue())) {
                useCase.handleCreate();
            } else if (channelName.equals(VirtualDriveChannels.VIRTUAL_DRIVE_DELETE.getValue())) {
                useCase.handleDelete();
            } else if (channelName.equals(VirtualDriveChannels.VIRTUAL_DRIVE_RENAME.getValue())) {
                useCase.handleRename();
            } else if (channelName.equals(VirtualDriveChannels.VIRTUAL_DRIVE_TRUNCATE.getValue())) {
                useCase.handleTruncate();
            } else {
                Log.w(TAG, "No dispatch for unknown VD channel: " + channelName);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error handling VD channel [" + channelName + "]: " + e.getMessage(), e);
        }
    }

    @Override
    public void onShutdown() {
        // No persistent resources to release — data threads hold their own references
        // and will complete or be interrupted when the process exits.
        Log.d(TAG, "VirtualDriveChannelHandler shut down for: " + channelName);
    }
}

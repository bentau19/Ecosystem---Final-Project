package com.example.android.network.handlers;

import android.util.Log;

import com.example.android.domain.usecases.VirtualDriveUseCase;
import com.example.android.enums.VirtualDriveChannels;

/**
 * {@link ChannelHandler} for all virtual-drive TauSync channels.
 *
 * <p>One instance of this class is registered <em>per op-type</em> in
 * {@link com.example.android.services.ConnectivityService#registerChannelHandlers()},
 * keyed under the prefix {@code getValue() + "_"} (e.g. {@code "virtual_drive_list_"}).
 * The {@link ChannelHandlerRegistry} prefix-fallback routes every UUID-suffixed incoming
 * channel (e.g. {@code "virtual_drive_list_a1b2c3d4"}) to the matching instance without
 * requiring any changes to the registry itself.
 *
 * <p>When the polling loop detects that the PC has a waiting request for a virtual-drive
 * channel, the registry calls {@link #onPeerRequest(String)} with the <em>full</em>
 * channel name (including UUID suffix).  This handler uses {@code startsWith} on the base
 * value to identify the op, then delegates to the appropriate {@link VirtualDriveUseCase}
 * method, forwarding the full channel name so the use-case can connect on the correct
 * unique meeting word.
 *
 * <p>All delegated methods block briefly on the network I/O for the request/response
 * phase on {@code PeerRequestHandlerThread}.  Heavy data I/O (file reads/writes) is
 * performed inline on that same thread — the transport layer's
 * {@code serveJsonThenStreamOut} / {@code serveJsonHeaderThenStreamIn} handle chunked
 * streaming without buffering the entire file.
 *
 * <p>No persistent state is held here; {@link #onShutdown()} is a no-op.
 */
public class VirtualDriveChannelHandler implements ChannelHandler {

    private static final String TAG = "VDriveHandler";

    /** Base value of the op this instance handles (e.g. {@code "virtual_drive_list"}). */
    private final String baseChannelName;
    private final VirtualDriveUseCase useCase;

    /**
     * @param baseChannelName The base meeting-word value this instance handles
     *                        (a {@link VirtualDriveChannels#getValue()} result,
     *                        e.g. {@code "virtual_drive_list"}).
     * @param useCase         Shared {@link VirtualDriveUseCase} — thread-safe, may be
     *                        called concurrently from different handler instances.
     */
    public VirtualDriveChannelHandler(String baseChannelName, VirtualDriveUseCase useCase) {
        this.baseChannelName = baseChannelName;
        this.useCase         = useCase;
    }

    /**
     * Returns the prefix key under which this handler is registered in the
     * {@link ChannelHandlerRegistry} (base name + {@code "_"}).
     *
     * <p>The registry's prefix-fallback uses {@code channel.startsWith(key)}, so
     * {@code "virtual_drive_list_a1b2c3d4"} is correctly routed to the
     * {@code "virtual_drive_list_"} entry.
     */
    @Override
    public String getChannelName() {
        return baseChannelName + "_";
    }

    /**
     * Not called — the registry always dispatches via {@link #onPeerRequest(String)}.
     * Logs a warning if somehow invoked without the full channel name.
     */
    @Override
    public void onPeerRequest() {
        Log.w(TAG, "onPeerRequest() called without channel name for base ["
                + baseChannelName + "] — ignored");
    }

    /**
     * Dispatches to the correct {@link VirtualDriveUseCase} method based on which
     * {@link VirtualDriveChannels} base prefix {@code channel} starts with.
     *
     * <p>Called by {@link ChannelHandlerRegistry} on {@code PeerRequestHandlerThread}.
     * The full channel name (including UUID suffix) is forwarded to the use-case so it
     * can connect on the exact unique meeting word the desktop opened.
     *
     * @param channel Full channel name, e.g. {@code "virtual_drive_stat_a1b2c3d4"}.
     */
    @Override
    public void onPeerRequest(String channel) {
        try {
            // IMPORTANT: check VIRTUAL_DRIVE_LIST_PAGE before VIRTUAL_DRIVE_LIST because
            // "virtual_drive_list_page_" starts with "virtual_drive_list_" — the longer
            // (more specific) prefix must be matched first.
            if (channel.startsWith(VirtualDriveChannels.VIRTUAL_DRIVE_LIST_PAGE.getValue() + "_")) {
                useCase.handleListPage(channel);
            } else if (channel.startsWith(VirtualDriveChannels.VIRTUAL_DRIVE_LIST.getValue() + "_")) {
                useCase.handleList(channel);
            } else if (channel.startsWith(VirtualDriveChannels.VIRTUAL_DRIVE_STAT.getValue() + "_")) {
                useCase.handleStat(channel);
            } else if (channel.startsWith(VirtualDriveChannels.VIRTUAL_DRIVE_READ.getValue() + "_")) {
                useCase.handleRead(channel);
            } else if (channel.startsWith(VirtualDriveChannels.VIRTUAL_DRIVE_WRITE.getValue() + "_")) {
                useCase.handleWrite(channel);
            } else if (channel.startsWith(VirtualDriveChannels.VIRTUAL_DRIVE_CREATE.getValue() + "_")) {
                useCase.handleCreate(channel);
            } else if (channel.startsWith(VirtualDriveChannels.VIRTUAL_DRIVE_DELETE.getValue() + "_")) {
                useCase.handleDelete(channel);
            } else if (channel.startsWith(VirtualDriveChannels.VIRTUAL_DRIVE_RENAME.getValue() + "_")) {
                useCase.handleRename(channel);
            } else if (channel.startsWith(VirtualDriveChannels.VIRTUAL_DRIVE_TRUNCATE.getValue() + "_")) {
                useCase.handleTruncate(channel);
            } else {
                Log.w(TAG, "No dispatch for unknown VD channel: " + channel);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error handling VD channel [" + channel + "]: " + e.getMessage(), e);
        }
    }

    @Override
    public void onShutdown() {
        // No persistent resources to release — the transport layer manages its own
        // TauSyncStream lifecycle inside each serveJson* call.
        Log.d(TAG, "VirtualDriveChannelHandler shut down for base: " + baseChannelName);
    }
}

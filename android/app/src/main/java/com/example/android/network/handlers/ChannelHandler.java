package com.example.android.network.handlers;

/**
 * ChannelHandler interface defines a contract for handling peer requests for a specific channel.
 *
 * This enables a plugin-like architecture where different channels (battery, PC name, storage, etc.)
 * can be handled independently through specialized handlers.
 *
 * Benefits:
 * ✓ Easy to add new channels (just create a new handler)
 * ✓ Decoupled from ConnectivityService
 * ✓ Each handler can have its own logic and dependencies
 * ✓ Future features (clipboard, file transfer) can be added as new handlers
 */
public interface ChannelHandler {

    /**
     * Gets the channel name this handler is responsible for.
     * Should match a value from DeviceInfoChannels enum.
     */
    String getChannelName();

    /**
     * Called when the peer (PC) has a request for this channel.
     *
     * The handler should:
     * 1. Read data from the channel if needed
     * 2. Process the request
     * 3. Write response back to the channel if needed
     * 4. Update the repository if state changed
     *
     * This method is called from the main thread in a safe context.
     */
    void onPeerRequest();

    /**
     * Called with the exact peer channel name that triggered dispatch.
     *
     * <p>Used by prefix-matched handlers (e.g. {@code BackupReceivedChannelHandler}
     * registered under {@code "backup_file_result_"}) that need the full channel name
     * to extract a dynamic suffix (e.g. the slot index).
     *
     * <p>Default implementation delegates to {@link #onPeerRequest()} so all existing
     * handlers require <b>zero changes</b>.
     *
     * @param channel The exact channel name as returned by {@code getPeerWaitingWords()}.
     */
    default void onPeerRequest(String channel) {
        onPeerRequest();
    }

    /**
     * Called when the handler should clean up resources.
     * This is called during service shutdown.
     */
    void onShutdown();
}


package com.example.android.network.transport;

import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.utils.NetworkHandler;
import com.example.tausync_lib.sdk.TauSync;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * TauSyncTransportManager - Concrete implementation of TransportManager for TauSync.
 *
 * Responsibilities:
 * ✓ Manages TauSync connection lifecycle
 * ✓ Implements automatic reconnection with exponential backoff
 * ✓ Provides periodic polling for peer requests
 * ✓ Handles graceful shutdown and resource cleanup
 * ✓ Decouples ConnectivityService from TauSync implementation details
 *
 */
public class TauSyncTransportManager implements TransportManager {

    private static final String TAG = "TauSyncTransport";

    // Retry configuration
    private static final int INITIAL_RETRY_DELAY_MS = 1000;      // 1 second
    private static final int MAX_RETRY_DELAY_MS = 30000;         // 30 seconds
    private static final int MAX_RETRY_ATTEMPTS = 2;
    private static final int POLLING_INTERVAL_MS = 2000;         // 2 seconds

    // State management
    private final AtomicBoolean isShuttingDown = new AtomicBoolean(false);
    private TransportStatus status = TransportStatus.IDLE;
    private TransportListener listener;
    private TauSync tauSync;
    private RemoteDeviceInfo currentRemoteDevice;

    // Threading
    private final ExecutorService connectionExecutor = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "TauSync-Connection");
        thread.setDaemon(true);
        return thread;
    });

    private ScheduledExecutorService pollingExecutor;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    // Reconnection tracking
    private int currentRetryAttempt = 0;
    private long nextRetryDelayMs = INITIAL_RETRY_DELAY_MS;

    @Override
    public void connect(RemoteDeviceInfo remoteDevice, TransportListener transportListener) {
        if (status == TransportStatus.CONNECTING || status == TransportStatus.CONNECTED) {
            Log.w(TAG, "Already connected or connecting. Skipping duplicate connect request.");
            return;
        }

        this.currentRemoteDevice = remoteDevice;
        this.listener = transportListener;
        this.currentRetryAttempt = 0;
        this.nextRetryDelayMs = INITIAL_RETRY_DELAY_MS;

        updateStatus(TransportStatus.CONNECTING);
        attemptConnection();
    }

    /**
     * Internal method that handles the actual connection attempt with retry logic.
     */
    private void attemptConnection() {
        if (isShuttingDown.get() || currentRemoteDevice == null) {
            Log.w(TAG, "Attempt connection bypassed: Manager is shutting down or device is null.");
            return;
        }

        connectionExecutor.execute(() -> {
            Log.d(TAG, "🔵 Thread started, about to call connectTo");
            try {
                // Notify listener of reconnect attempt (only if this is a retry)
                if (currentRetryAttempt > 0 && listener != null) {
                    mainHandler.post(() -> listener.onReconnectAttempt(currentRetryAttempt, MAX_RETRY_ATTEMPTS));
                }

                tauSync = new TauSync();
                Log.d(TAG, "🔵 TauSync created, calling connectTo...");

                // connect to PC with tauSync
                // 5 sec timeout
                java.util.concurrent.Future<?> connectFuture = java.util.concurrent.Executors
                        .newSingleThreadExecutor()
                        .submit(() -> tauSync.connectTo(currentRemoteDevice.getPcIp()));

                try {
                    connectFuture.get(5, java.util.concurrent.TimeUnit.SECONDS);
                } catch (java.util.concurrent.TimeoutException e) {
                    connectFuture.cancel(true);
                    throw new Exception("Connection timed out after 5 seconds");
                }

                // connect success
                Log.d(TAG, "🟢 connectTo returned successfully");

                currentRetryAttempt = 0;
                nextRetryDelayMs = INITIAL_RETRY_DELAY_MS;

                updateStatus(TransportStatus.CONNECTED);
                startPollingForPeerRequests();

            } catch (Exception e) {
                Log.e(TAG, "🔴 CAUGHT exception: " + e.getClass().getName() + " - " + e.getMessage());

//              TODO: error even after failure still connect regulatory.
                handleConnectionFailure(e);
            } catch (Throwable t) {
                Log.e(TAG, "🔴 CAUGHT throwable: " + t.getClass().getName() + " - " + t.getMessage());
            }
        });
    }

    /**
     * Handles connection failure and decides whether to retry.
     * Implements exponential backoff with jitter.
     */
    private void handleConnectionFailure(Exception error) {
        currentRetryAttempt++;

        if (currentRetryAttempt >= MAX_RETRY_ATTEMPTS) {
            // Max retries exhausted
            Log.e(TAG, "✘ Failed to connect after " + MAX_RETRY_ATTEMPTS + " attempts.");
            updateStatus(TransportStatus.FAILED);
            if (listener != null) {
                mainHandler.post(() -> listener.onConnectionError(error));
            }
        } else {
            // Schedule retry with exponential backoff
            updateStatus(TransportStatus.RECONNECTING);

            // Add jitter to prevent thundering herd
            long jitter = (long) (Math.random() * 1000);
            long delayWithJitter = nextRetryDelayMs + jitter;

            Log.i(TAG, "Scheduling retry #" + currentRetryAttempt + " in " + delayWithJitter + "ms");

            mainHandler.postDelayed(
                    this::attemptConnection,
                    delayWithJitter
            );

            // Calculate next retry delay (exponential backoff: cap at MAX_RETRY_DELAY_MS)
            nextRetryDelayMs = Math.min(
                    nextRetryDelayMs * 2,
                    MAX_RETRY_DELAY_MS
            );
        }
    }

    /**
     * Starts the polling loop that checks for peer requests periodically.
     * Creates new ScheduledExecutorService for polling.
     */
    private void startPollingForPeerRequests() {
        if (isShuttingDown.get()) {
            return;
        }

        // Create polling executor if needed
        if (pollingExecutor == null || pollingExecutor.isShutdown()) {
            pollingExecutor = Executors.newScheduledThreadPool(1, runnable -> {
                Thread thread = new Thread(runnable, "TauSync-Polling");
                thread.setDaemon(true);
                return thread;
            });
        }

        pollingExecutor.scheduleWithFixedDelay(() -> {
            if (isShuttingDown.get() || status != TransportStatus.CONNECTED) {
                return;
            }

            try {
                List<String> waitingChannels = tauSync.getPeerWaitingWords();
                if (!waitingChannels.isEmpty() && listener != null) {
                    mainHandler.post(() -> listener.onPeerRequestsAvailable(waitingChannels));
                }
            } catch (Exception e) {
                Log.e(TAG, "Error polling for peer requests: " + e.getMessage());
                // Treat polling error as connection failure - initiate reconnect
                handlePollingFailure(e);
            }
        }, POLLING_INTERVAL_MS, POLLING_INTERVAL_MS, TimeUnit.MILLISECONDS);

        Log.d(TAG, "Started polling loop with " + POLLING_INTERVAL_MS + "ms interval");
    }

    /**
     * Handles errors during polling phase.
     * Triggers reconnection sequence.
     */
    private void handlePollingFailure(Exception error) {
        Log.w(TAG, "Connection lost during polling. Initiating reconnection sequence.");

        // Clean up TauSync
        if (tauSync != null) {
            try {
                tauSync.dispose();
            } catch (Exception e) {
                Log.d(TAG, "Error disposing TauSync: " + e.getMessage());
            }
            tauSync = null;
        }

        // Stop polling
        stopPolling();

        // Reconnect if we were actively connected
        if (status == TransportStatus.CONNECTED) {
            attemptConnection();
        }
    }

    /**
     * Stops the polling executor safely.
     */
    private void stopPolling() {
        if (pollingExecutor != null && !pollingExecutor.isShutdown()) {
            try {
                pollingExecutor.shutdown();
                if (!pollingExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                    Log.w(TAG, "Polling executor did not terminate gracefully, forcing shutdown");
                    pollingExecutor.shutdownNow();
                }
            } catch (InterruptedException e) {
                pollingExecutor.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }

    @Override
    public void writeToChannel(String channel, String data) throws Exception {
        if (tauSync != null && status == TransportStatus.CONNECTED) {
            NetworkHandler.writeToChannel(tauSync, channel, data);
            Log.v(TAG, "Written to channel [" + channel + "]: " + data);
        } else {
            throw new IllegalStateException("Cannot write to channel [" + channel + "]: Not connected");
        }
    }

    @Override
    public String readFromChannel(String channel) throws Exception {
        if (tauSync != null && status == TransportStatus.CONNECTED) {
            String data = NetworkHandler.readFromChannel(tauSync, channel);
            Log.v(TAG, "Read from channel [" + channel + "]: " + data);
            return data != null ? data : "";
        }
        throw new IllegalStateException("Cannot read from channel [" + channel + "]: Not connected");
    }

    @Override
    public void disconnect() {
        Log.d(TAG, "Disconnect requested");
        mainHandler.removeCallbacks(this::attemptConnection);

        updateStatus(TransportStatus.DISCONNECTING);

        // Stop polling
        stopPolling();

        // Dispose TauSync connection
        if (tauSync != null) {
            try {
                tauSync.dispose();
                Log.d(TAG, "TauSync disposed");
            } catch (Exception e) {
                Log.d(TAG, "Error during TauSync disposal: " + e.getMessage());
            }
            tauSync = null;
        }

        updateStatus(TransportStatus.IDLE);
        currentRetryAttempt = 0;
        currentRemoteDevice = null;
    }

    @Override
    public boolean isConnected() {
        return status == TransportStatus.CONNECTED;
    }

    @Override
    public TransportStatus getStatus() {
        return status;
    }

    @Override
    public void shutdown() {
        Log.d(TAG, "⚠️ Shutdown called from: " + Arrays.toString(Thread.currentThread().getStackTrace()));
        isShuttingDown.set(true);

        disconnect();

        try {
            connectionExecutor.shutdown();
            if (!connectionExecutor.awaitTermination(20, TimeUnit.SECONDS)) {
                Log.w(TAG, "Connection executor did not terminate gracefully, forcing shutdown");
                connectionExecutor.shutdownNow();
            }
        } catch (InterruptedException e) {
            connectionExecutor.shutdownNow();
            Thread.currentThread().interrupt();
        }

        Log.d(TAG, "Shutdown complete");
    }

    /**
     * Updates the transport status and notifies the listener via main handler.
     */
    private void updateStatus(TransportStatus newStatus) {
        if (status != newStatus) {
            status = newStatus;
            Log.d(TAG, "Transport status changed to: " + newStatus);
            if (listener != null) {
                mainHandler.post(() -> listener.onStatusChanged(newStatus));
            }
        }
    }
}


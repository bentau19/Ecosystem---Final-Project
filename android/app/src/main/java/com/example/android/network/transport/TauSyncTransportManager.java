package com.example.android.network.transport;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionType;
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
 * <p>
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
    private static final int POLLING_INTERVAL_MS = 20;           // 20 ms — avg discovery latency
    // 10 ms instead of 50 ms; 5×
    // faster virtual-drive op pickup

    // Hybrid (Bluetooth) connect timeouts. Bluetooth is slower than Wi-Fi, and the device is
    // already bonded by the discovery flow, so the link + handshake take a few seconds. The inner
    // timeout is shorter than the outer Future timeout so the inner thread always exits first.
    private static final int BT_CONNECT_INNER_TIMEOUT_SECONDS = 10;
    private static final int BT_CONNECT_OUTER_TIMEOUT_SECONDS = 11;

    // State management
    private final AtomicBoolean isShuttingDown = new AtomicBoolean(false);
    // volatile: written on sendDisconnectToPC / PeerRequestHandler threads, read on the
    // polling executor thread. Without volatile the polling thread can see a stale CONNECTED
    // value after prepareForDisconnect() sets DISCONNECTING, causing a spurious reconnect.
    private volatile TransportStatus status = TransportStatus.IDLE;
    private TransportListener listener;
    private TauSync tauSync;
    private RemoteDeviceInfo currentRemoteDevice;

    // Application context for the hybrid connectHybrid(context, mac) call. Stored as the
    // application context (not the Service) so this long-lived manager can never pin a
    // destroyed Service in memory.
    private final Context applicationContext;

    // Threading
    private final ExecutorService connectionExecutor = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "TauSync-Connection");
        thread.setDaemon(true);
        return thread;
    });

    private ScheduledExecutorService pollingExecutor;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    // Stable Runnable identity for mainHandler.postDelayed / removeCallbacks.
    // In Java, `this::attemptConnection` creates a NEW object on every evaluation,
    // so two separate `this::attemptConnection` expressions are never == to each
    // other.  Handler.removeCallbacks(r) matches by reference (==), meaning
    // removeCallbacks(this::attemptConnection) would silently fail to remove a
    // previously posted this::attemptConnection callback.  Storing the reference
    // once guarantees postDelayed and removeCallbacks see the same object.
    private final Runnable retryConnectionRunnable = this::attemptConnection;

    // Reconnection tracking
    private int currentRetryAttempt = 0;
    private long nextRetryDelayMs = INITIAL_RETRY_DELAY_MS;

    /**
     * @param context any Context; the application context is extracted defensively so a Service
     *                context can never be retained by this long-lived manager.
     */
    public TauSyncTransportManager(Context context) {
        this.applicationContext = context.getApplicationContext();
    }

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

                // Disconnect any TauSync instance left over from a prior timed-out
                // attempt.  connectTo() below spawns an inner thread that can outlive
                // the outer Future.get() timeout; without this cleanup that orphaned
                // thread can connect to the PC's freshly restarted listener after a
                // phone-initiated disconnect, producing a spurious second "d" on the PC.
                TauSync previousTauSync = tauSync;
                tauSync = null;
                if (previousTauSync != null) {
                    try {
                        previousTauSync.disconnect();
                    } catch (Exception ignored) {
                    }
                }

                tauSync = new TauSync();
                Log.d(TAG, "🔵 TauSync created, calling connectTo...");

                // connect to PC with tauSync. The inner TauSync timeout is intentionally shorter
                // than the outer Java Future timeout so the inner thread always exits before
                // Future.get() times out.  This prevents an orphaned native thread from lingering
                // and later connecting to the PC's next listener session.
                //
                // Route by connection type: BLUETOOTH runs the hybrid connect (Bluetooth primary +
                // lazy Wi-Fi) by MAC; everything else is the existing Wi-Fi connect by IP. The
                // hybrid call gets the application context so this manager can't pin a Service.
                final boolean hybrid =
                        currentRemoteDevice.getConnectionType() == ConnectionType.BLUETOOTH;
                final int outerTimeoutSeconds = hybrid ? BT_CONNECT_OUTER_TIMEOUT_SECONDS : 5;

                java.util.concurrent.Future<?> connectFuture = java.util.concurrent.Executors
                        .newSingleThreadExecutor()
                        .submit(() -> {
                            if (hybrid) {
                                tauSync.connectHybrid(
                                        applicationContext,
                                        currentRemoteDevice.getMacAddress(),
                                        BT_CONNECT_INNER_TIMEOUT_SECONDS);
                            } else {
                                tauSync.connectTo(currentRemoteDevice.getPcIp(), 4);
                            }
                        });

                try {
                    connectFuture.get(outerTimeoutSeconds, java.util.concurrent.TimeUnit.SECONDS);
                } catch (java.util.concurrent.TimeoutException e) {
                    connectFuture.cancel(true);
                    throw new Exception("Connection timed out after " + outerTimeoutSeconds + " seconds");
                }

                // connect success
                Log.d(TAG, "🟢 connect returned successfully (hybrid=" + hybrid + ")");

                currentRetryAttempt = 0;
                nextRetryDelayMs = INITIAL_RETRY_DELAY_MS;

                updateStatus(TransportStatus.CONNECTED);
                startPollingForPeerRequests();

            } catch (Exception e) {
                Log.e(TAG, "🔴 CAUGHT exception: " + e.getClass().getName() + " - " + e.getMessage());
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
                    retryConnectionRunnable,
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
            // tauSync may be null during the reconnect window (handlePollingFailure
            // has already cleared it before attemptConnection creates the new instance).
            if (isShuttingDown.get() || status != TransportStatus.CONNECTED || tauSync == null) {
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

        // Close the dead TauSync socket.
        // Use disconnect() — NOT dispose().  dispose() permanently poisons the C# singleton
        // globalRole, preventing any future TauSync() instance from connecting.  disconnect()
        // cleanly closes the TCP socket while leaving globalRole intact for the reconnect.
        if (tauSync != null) {
            try {
                tauSync.disconnect();
            } catch (Exception e) {
                Log.d(TAG, "Error closing TauSync during polling failure: " + e.getMessage());
            }
            tauSync = null;
        }

        // Do NOT call stopPolling() here.  stopPolling() calls
        // pollingExecutor.awaitTermination() which self-deadlocks when invoked from within
        // a polling-executor task (the task waits for itself to finish — 5-second timeout).
        // shutdownNow() marks the executor for shutdown without blocking; the current task
        // completes normally and no further tasks are scheduled.  startPollingForPeerRequests()
        // detects isShutdown() == true and creates a fresh executor on the next connect.
        if (pollingExecutor != null && !pollingExecutor.isShutdown()) {
            pollingExecutor.shutdownNow();
        }

        // Reconnect only if we were actively connected AND a deliberate shutdown is not
        // already in progress. isShuttingDown is set at the top of shutdown() (called by
        // cleanup() from DisconnectChannelHandler / sendDisconnectToPC). Without this guard
        // a polling failure that races with cleanup causes an unwanted reconnect attempt —
        // the "auto send connect_to_pc" bug.
//        if (status == TransportStatus.CONNECTED && !isShuttingDown.get()) {
//            attemptConnection();
//        }
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

    /**
     * Default connect timeout for one-shot control channels (meta, config, etc.).
     * Large data channels use a file-size-proportional timeout passed by the caller.
     */
    private static final int DEFAULT_WRITE_CONNECT_TIMEOUT_S = 30;

    /**
     * Stops the polling loop and transitions the transport to
     * {@link TransportStatus#DISCONNECTING}, <em>without</em> closing the underlying
     * socket or resetting the retry / device state.
     *
     * <p>Call this from {@code sendDisconnectToPC()} before calling
     * {@link #writeToChannel} so the 20 ms polling tick can no longer race with
     * the outbound {@code tauSync.connect()} call.  Without this guard the poll
     * occasionally fails → {@code handlePollingFailure} → socket disposed →
     * desktop never joins the {@code disconnect_phone} word → Android stalls for
     * up to 30 s waiting for the connect timeout.
     *
     * <p>This method blocks briefly (up to 5 s via {@link #stopPolling}) waiting
     * for any in-flight polling task to finish.  Always call from a background
     * thread — never from the main thread.
     */
    @Override
    public void prepareForDisconnect() {
        if (isShuttingDown.get()) {
            Log.d(TAG, "prepareForDisconnect: already shutting down, skipping");
            return;
        }
        mainHandler.removeCallbacks(retryConnectionRunnable);
        updateStatus(TransportStatus.DISCONNECTING);
        stopPolling();  // blocks until any in-flight getPeerWaitingWords() completes
        Log.d(TAG, "prepareForDisconnect: polling stopped, ready to send disconnect signal");
    }

    /**
     * Writes a UTF-8 string to a TauSync channel.
     *
     * <p><b>Unlike {@link NetworkHandler#writeToChannel}</b>, this method does NOT
     * swallow exceptions — any failure propagates to the caller so that upstream code
     * (e.g. {@code BackupTransferUseCase}) can correctly distinguish a failed send
     * from a successful one and set {@code metaSent} accordingly.
     *
     * <p>Allowed in both {@link TransportStatus#CONNECTED} and
     * {@link TransportStatus#DISCONNECTING} states so that
     * {@code sendDisconnectToPC()} can write the farewell channel after
     * {@link #prepareForDisconnect()} has already set the status.
     */
    @Override
    public void writeToChannel(String channel, String data) throws Exception {
        writeToChannel(channel, data, DEFAULT_WRITE_CONNECT_TIMEOUT_S);
    }

    @Override
    public void writeToChannel(String channel, String data, int timeoutSec) throws Exception {
        if (tauSync == null || (status != TransportStatus.CONNECTED && status != TransportStatus.DISCONNECTING)) {
            throw new IllegalStateException(
                    "Cannot write to channel [" + channel + "]: Not connected");
        }
        try (com.example.tausync_lib.implementations.management.TauSyncStream stream =
                     tauSync.connect(channel, timeoutSec)) {
            stream.writeString(data);
        }
        Log.v(TAG, "Written to channel [" + channel + "]: " + data);
    }

    @Override
    public String readFromChannel(String channel) throws Exception {
        return readFromChannel(channel, DEFAULT_WRITE_CONNECT_TIMEOUT_S);
    }

    /**
     * Reads a UTF-8 string from a TauSync channel, waiting up to {@code connectTimeoutSec}
     * seconds for the peer to open the same channel.
     *
     * <p>Use for result channels where the peer may take longer than the default 30 s
     * (e.g. a backup result channel whose PC-side processing includes ML classification
     * and a file copy before the result is sent).
     */
    @Override
    public String readFromChannel(String channel, int connectTimeoutSec) throws Exception {
        if (tauSync == null || status != TransportStatus.CONNECTED) {
            throw new IllegalStateException(
                    "Cannot read from channel [" + channel + "]: Not connected");
        }
        try (com.example.tausync_lib.implementations.management.TauSyncStream stream =
                     tauSync.connect(channel, connectTimeoutSec)) {
            String data = new String(stream.readAll(), java.nio.charset.StandardCharsets.UTF_8);
            Log.v(TAG, "Read from channel [" + channel + "]: " + data);
            return data;
        }
    }

    @Override
    public byte[] readBytesFromChannel(String channel) throws Exception {
        if (tauSync != null && status == TransportStatus.CONNECTED) {
            byte[] data = NetworkHandler.readBytesFromChannel(tauSync, channel);
            Log.v(TAG, "Read " + data.length + " bytes from channel [" + channel + "]");
            return data;
        }
        throw new IllegalStateException("Cannot read bytes from channel [" + channel + "]: Not connected");
    }

    private static final int FILE_CHUNK_SIZE = 65536; // 64 KB — matches TauSync's default chunk size

    /**
     * Streams bytes from a TauSync channel directly into the provided OutputStream.
     * Reads in 64 KB chunks until the peer sends FIN (EOF), so the entire file is
     * never held in RAM — safe for arbitrarily large files.
     */
    @Override
    public void streamChannelToOutputStream(String channel, java.io.OutputStream outputStream) throws Exception {
        if (tauSync == null || status != TransportStatus.CONNECTED) {
            throw new IllegalStateException("Cannot stream from channel [" + channel + "]: Not connected");
        }

        try (com.example.tausync_lib.implementations.management.TauSyncStream stream = tauSync.connect(channel)) {
            java.io.InputStream in = stream.getInputStream();
            byte[] buf = new byte[FILE_CHUNK_SIZE];
            int n;
            long totalBytes = 0;
            int chunkCount = 0;
            while ((n = in.read(buf, 0, buf.length)) > 0) {
                outputStream.write(buf, 0, n);
                totalBytes += n;
                chunkCount++;
            }
            Log.d(TAG, "Streamed " + totalBytes + " bytes in " + chunkCount + " chunks from [" + channel + "]");
        }
    }

    /**
     * Streams bytes from the provided InputStream into a TauSync channel.
     * Reads in 64 KB chunks until the InputStream is exhausted (EOF), then flushes
     * so the peer's read_to_file() sees a clean EOF and returns.
     * No full-file buffering in RAM — safe for arbitrarily large files.
     *
     * <p>Uses the default 30-second connect timeout. For file-size-proportional
     * timeouts (e.g. backup data slots) use
     * {@link #streamInputStreamToChannel(String, java.io.InputStream, int)}.
     */
    @Override
    public void streamInputStreamToChannel(String channel, java.io.InputStream inputStream) throws Exception {
        streamInputStreamToChannel(channel, inputStream, 30);
    }

    /**
     * Same as {@link #streamInputStreamToChannel(String, java.io.InputStream)} but
     * uses {@code connectTimeoutSec} for the TauSync channel handshake instead of
     * the default 30 s.  Use for backup data slots whose file-size-proportional
     * connect timeout can greatly exceed 30 s for large files.
     */
    @Override
    public void streamInputStreamToChannel(String channel,
                                           java.io.InputStream inputStream,
                                           int connectTimeoutSec) throws Exception {
        if (tauSync == null || status != TransportStatus.CONNECTED) {
            throw new IllegalStateException("Cannot stream to channel [" + channel + "]: Not connected");
        }

        try (com.example.tausync_lib.implementations.management.TauSyncStream stream =
                     tauSync.connect(channel, connectTimeoutSec)) {
            java.io.OutputStream out = stream.getOutputStream();
            byte[] buf = new byte[FILE_CHUNK_SIZE];
            int n;
            long totalBytes = 0;
            int chunkCount = 0;
            while ((n = inputStream.read(buf, 0, buf.length)) > 0) {
                out.write(buf, 0, n);
                totalBytes += n;
                chunkCount++;
            }
            out.flush();
            Log.d(TAG, "Streamed " + totalBytes + " bytes in " + chunkCount
                    + " chunks to [" + channel + "] (connectTimeout=" + connectTimeoutSec + "s)");
        }
    }

    /**
     * Opens a single TauSync channel, writes UTF-8 metadata + {@code '\n'}, then
     * streams all bytes from {@code inputStream} before closing the channel.
     *
     * <p>A single {@code tauSync.connect(channel)} is used for both the metadata write
     * and the binary stream, avoiding the 2-second ID-recycling grace period that would
     * result from two consecutive {@code connect()} calls on the same channel name.
     *
     * <p>The PC reads up to the first {@code '\n'} to obtain the JSON metadata, then
     * treats the remainder of the stream as raw file bytes.
     */
    @Override
    public void writeMetadataThenStreamToChannel(String channel,
                                                 String metadata,
                                                 java.io.InputStream inputStream) throws Exception {
        if (tauSync == null || status != TransportStatus.CONNECTED) {
            throw new IllegalStateException(
                    "Cannot write to channel [" + channel + "]: Not connected");
        }

        try (com.example.tausync_lib.implementations.management.TauSyncStream stream =
                     tauSync.connect(channel)) {
            java.io.OutputStream out = stream.getOutputStream();

            // ── 1. Metadata line ──────────────────────────────────────────────
            byte[] metaBytes = (metadata + "\n")
                    .getBytes(java.nio.charset.StandardCharsets.UTF_8);
            out.write(metaBytes);

            // ── 2. Raw file bytes ─────────────────────────────────────────────
            byte[] buf = new byte[FILE_CHUNK_SIZE];
            int n;
            long totalBytes = 0;
            int chunkCount = 0;
            while ((n = inputStream.read(buf, 0, buf.length)) > 0) {
                out.write(buf, 0, n);
                totalBytes += n;
                chunkCount++;
            }
            out.flush();
            Log.d(TAG, "writeMetadataThenStreamToChannel [" + channel + "]: meta="
                    + metaBytes.length + "B + data=" + totalBytes
                    + "B in " + chunkCount + " chunks");
        }
    }

    @Override
    public void serveJsonExchange(String channel, JsonExchangeHandler handler) throws Exception {
        if (tauSync == null || status != TransportStatus.CONNECTED) {
            throw new IllegalStateException(
                    "Cannot serve channel [" + channel + "]: Not connected");
        }
        try (com.example.tausync_lib.implementations.management.TauSyncStream stream =
                     tauSync.connect(channel)) {
            Log.d(TAG, "serveJsonExchange: connected");
            // Read the newline-terminated JSON request the peer wrote.
            // readLine() returns at '\n' without waiting for the peer to close the stream,
            // which avoids the mutual-readAll deadlock (both sides waiting for the other's FIN).
            String request = stream.readLine();
            if (request == null) {
                throw new java.io.EOFException(
                        "serveJsonExchange: peer closed without sending request on [" + channel + "]");
            }
            Log.d(TAG, "serveJsonExchange: request:-----    " + request + " -------");
            // Compute the response (may spawn background threads for data-phase ops).
            // The full JSON request is forwarded — every handler parses the fields
            // it needs (path, offset, length, uuid, from, to, ...) from it.
            String response = handler.respond(request);

            Log.d(TAG, "serveJsonExchange: response= " + response);
            // Write the response back on the same stream before it closes.
            stream.writeString(response);
            Log.v(TAG, "serveJsonExchange [" + channel + "]: req=" + request
                    + " resp=" + response);
        }
    }

    /**
     * Opens a single TauSync channel, reads one newline-terminated JSON request from the
     * peer, calls {@code handler} to obtain a source {@link java.io.InputStream}, and
     * streams all bytes from that stream back to the peer before closing the channel.
     *
     * <p>Used by the virtual-drive {@code read} op: the desktop opens
     * {@code virtual_drive_read_{uuid8}}, writes {@code {path, offset, length}\n}, and
     * reads the file bytes back.  The handler's {@code InputStream} is closed by this
     * method via try-with-resources; the outer {@code TauSyncStream} is closed immediately
     * after, sending FIN to the peer so {@code read_all()} on the desktop unblocks.
     */
    @Override
    public void serveJsonThenStreamOut(String channel, JsonToInputStreamHandler handler) throws Exception {
        if (tauSync == null || status != TransportStatus.CONNECTED) {
            throw new IllegalStateException(
                    "Cannot serve channel [" + channel + "]: Not connected");
        }
        try (com.example.tausync_lib.implementations.management.TauSyncStream stream =
                     tauSync.connect(channel, DEFAULT_WRITE_CONNECT_TIMEOUT_S)) {
            String request = stream.readLine();
            if (request == null) {
                throw new java.io.EOFException(
                        "serveJsonThenStreamOut: peer closed without sending request on ["
                                + channel + "]");
            }
            Log.d(TAG, "serveJsonThenStreamOut [" + channel + "]: req=" + request);
            try (java.io.InputStream in = handler.openInputStream(request)) {
                java.io.OutputStream out = stream.getOutputStream();
                byte[] buf = new byte[FILE_CHUNK_SIZE];
                int n;
                long totalBytes = 0;
                int chunkCount = 0;
                while ((n = in.read(buf, 0, buf.length)) > 0) {
                    out.write(buf, 0, n);
                    totalBytes += n;
                    chunkCount++;
                }
                out.flush();
                Log.d(TAG, "serveJsonThenStreamOut [" + channel + "]: streamed "
                        + totalBytes + "B in " + chunkCount + " chunks");
            }
        }
    }

    @Override
    public void serveReadRequest(String channel, JsonToReadResultHandler handler) throws Exception {
        if (tauSync == null || status != TransportStatus.CONNECTED) {
            throw new IllegalStateException(
                    "Cannot serve channel [" + channel + "]: Not connected");
        }
        try (com.example.tausync_lib.implementations.management.TauSyncStream stream =
                     tauSync.connect(channel, DEFAULT_WRITE_CONNECT_TIMEOUT_S)) {
            String request = stream.readLine();
            if (request == null) {
                throw new java.io.EOFException(
                        "serveReadRequest: peer closed without sending request on ["
                                + channel + "]");
            }
            Log.d(TAG, "serveReadRequest [" + channel + "]: req=" + request);

            ReadResult result;
            try {
                result = handler.openRead(request);
            } catch (Exception e) {
                // The handler is expected to map failures to error codes; an escape
                // here is unexpected — report it as io_error rather than streaming
                // nothing (which the peer could not distinguish from a clean EOF).
                Log.w(TAG, "serveReadRequest [" + channel + "]: handler threw", e);
                result = ReadResult.error("io_error");
            }

            if (!result.ok) {
                // Header only: the peer reads this line and surfaces the error.
                stream.writeString("{\"ok\":false,\"error\":\"" + result.error + "\"}\n");
                Log.d(TAG, "serveReadRequest [" + channel + "]: error=" + result.error);
                return;
            }

            // Success: declare the exact byte count, then stream exactly that many.
            stream.writeString("{\"ok\":true,\"length\":" + result.length + "}\n");
            try (java.io.InputStream in = result.stream) {
                java.io.OutputStream out = stream.getOutputStream();
                byte[] buf = new byte[FILE_CHUNK_SIZE];
                long remaining = result.length;
                while (remaining > 0) {
                    int want = (int) Math.min(buf.length, remaining);
                    int n = in.read(buf, 0, want);
                    if (n <= 0) break;  // file shrank under us → peer detects truncation
                    out.write(buf, 0, n);
                    remaining -= n;
                }
                out.flush();
                Log.d(TAG, "serveReadRequest [" + channel + "]: streamed "
                        + (result.length - remaining) + "/" + result.length + "B");
            }
        }
    }

    /**
     * Opens a single TauSync channel, reads one newline-terminated JSON header from the
     * peer, calls {@code handler} to obtain a destination {@link java.io.OutputStream},
     * and pipes all remaining bytes from the channel into that stream until the peer closes
     * it (EOF / FIN).  The handler's {@code OutputStream} is closed by this method via
     * try-with-resources; after this method returns the destination is fully written and
     * the caller should finalize (e.g. rename temp file).
     *
     * <p>Used by the virtual-drive {@code write} op: the desktop opens
     * {@code virtual_drive_write_{uuid8}}, writes {@code {path}\n} then pushes the file
     * bytes via internal {@code write} pipe ops, and finally closes on {@code write_close}.
     */
    @Override
    public void serveJsonHeaderThenStreamIn(String channel, JsonHeaderThenStreamInHandler handler) throws Exception {
        if (tauSync == null || status != TransportStatus.CONNECTED) {
            throw new IllegalStateException(
                    "Cannot serve channel [" + channel + "]: Not connected");
        }
        try (com.example.tausync_lib.implementations.management.TauSyncStream stream =
                     tauSync.connect(channel, DEFAULT_WRITE_CONNECT_TIMEOUT_S)) {
            String header = stream.readLine();
            if (header == null) {
                throw new java.io.EOFException(
                        "serveJsonHeaderThenStreamIn: peer closed without sending header on ["
                                + channel + "]");
            }
            Log.d(TAG, "serveJsonHeaderThenStreamIn [" + channel + "]: header=" + header);
            try (java.io.OutputStream dest = handler.openOutputStream(header)) {
                java.io.InputStream in = stream.getInputStream();
                byte[] buf = new byte[FILE_CHUNK_SIZE];
                int n;
                long totalBytes = 0;
                int chunkCount = 0;
                while ((n = in.read(buf, 0, buf.length)) > 0) {
                    dest.write(buf, 0, n);
                    totalBytes += n;
                    chunkCount++;
                }
                dest.flush();
                Log.d(TAG, "serveJsonHeaderThenStreamIn [" + channel + "]: received "
                        + totalBytes + "B in " + chunkCount + " chunks");
            }
        }
    }

    @Override
    public void disconnect() {
        Log.d(TAG, "Disconnect requested");
        mainHandler.removeCallbacks(retryConnectionRunnable);

        updateStatus(TransportStatus.DISCONNECTING);

        // Stop polling
        stopPolling();

        // Disconnect TauSync: closes the TCP socket and resets the global role
        // so that the next attemptConnection() can call connectTo() successfully.
        // disconnect() is used instead of dispose() because TauSyncTransportManager
        // creates a fresh TauSync() on every reconnect — dispose() would permanently
        // poison the singleton globalRole, preventing any future connection.
        if (tauSync != null) {
            try {
                tauSync.disconnect();
                Log.d(TAG, "TauSync disconnected");
            } catch (Exception e) {
                Log.d(TAG, "Error during TauSync disconnect: " + e.getMessage());
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
            // 5-second cap matches the connectTo() internal timeout — any in-flight
            // attemptConnection() task finishes within 5 s.  The previous 20-second
            // wait could block onDestroy() (which runs on the main thread) for far
            // longer than necessary.
            if (!connectionExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
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


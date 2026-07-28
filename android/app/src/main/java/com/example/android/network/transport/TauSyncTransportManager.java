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

    // Adaptive peer-request polling. A fixed 20 ms tick wakes the CPU 50×/second for the whole
    // session even when nothing is happening — a large idle battery cost. Instead the poll runs
    // fast only while requests are actually flowing and backs off once the link goes quiet; the
    // first request after a quiet period is picked up within POLLING_IDLE_INTERVAL_MS and the
    // loop immediately speeds back up for the rest of the burst.
    private static final int POLLING_INTERVAL_MS = 20;            // while requests are flowing
    private static final int POLLING_IDLE_INTERVAL_MS = 250;      // link quiet — let the CPU sleep
    private static final long POLLING_ACTIVE_WINDOW_MS = 5_000;   // stay fast this long after the last request

    // Epoch-ms of the last non-empty getPeerWaitingWords() result; drives the fast/idle decision.
    private volatile long lastPeerRequestMs = 0;

    // Incremented whenever a new polling session starts; a queued tick from a superseded session
    // sees a stale generation and exits, so two chains can never run concurrently.
    private final java.util.concurrent.atomic.AtomicInteger pollGeneration =
            new java.util.concurrent.atomic.AtomicInteger();

    // Hybrid (Bluetooth) connect timeouts. Bluetooth is slower than Wi-Fi, and the device is
    // already bonded by the discovery flow, so the link + handshake take a few seconds. The inner
    // timeout is shorter than the outer Future timeout so the inner thread always exits first.
    private static final int BT_CONNECT_INNER_TIMEOUT_SECONDS = 10;
    private static final int BT_CONNECT_OUTER_TIMEOUT_SECONDS = 11;

    // Extra wait granted when the PC announces APPROVAL_PENDING mid-handshake: the operator's
    // accept/reject dialog is open, so aborting at the normal timeout would kill a connection the
    // PC is about to accept. The PC auto-rejects at 55 s and the library handshake times out at
    // 60 s, so the in-flight connect always resolves (accept, reject, or timeout) within this.
    private static final int APPROVAL_WAIT_EXTENSION_SECONDS = 60;

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

<<<<<<< HEAD
=======
    // True while recovering an unexpectedly lost session. Unlike a user-initiated connect (which
    // gives up after MAX_RETRY_ATTEMPTS), recovery retries indefinitely with capped back-off —
    // the session should re-converge with zero taps whenever the PC comes back. Cleared on
    // success, on explicit disconnect/shutdown, and when the PC explicitly declines.
    private volatile boolean persistentReconnect = false;

>>>>>>> main
    // Connection-health watchdog. The PC only sends DISCONNECT_FROM_PC on a *clean* exit; a
    // crash / network drop just closes the socket. The poll loop checks tauSync.isConnected()
    // (which reflects the real socket and stays false while the transport transparently
    // reconnects) and only surfaces a disconnect if the link stays down past the grace window —
    // so a brief Wi-Fi blip (transport reconnects) never tears the session down.
    private static final long CONNECTION_LOST_GRACE_MS = 10_000L; // ~4 reconnect attempts; ≤10s UI lag
    // [0] = 0 when healthy, else epoch-ms of the first down tick. A 1-element holder (not a bare
    // long) so the pure static evaluateHealth() can update it. Touched only on the poll thread.
    private final long[] connectionLostSince = {0L};

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
            // A connect() arriving while one is already in flight or established is a duplicate
            // (e.g. a fragment's onResume auto-connect, or a service restart). Re-arming the
            // singleton transport would fail, so we still skip the reconnect — but we must NOT
            // return silently: a caller that already flipped its UI to "Connecting…" would hang
            // there until its own timeout. Echo the true current status so the UI reconciles.
            Log.w(TAG, "Duplicate connect request while " + status
                    + " — re-notifying status instead of reconnecting.");
            final TransportStatus current = status;
            if (transportListener != null) {
                mainHandler.post(() -> transportListener.onStatusChanged(current));
            }
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

                java.util.concurrent.ExecutorService connectRunner =
                        java.util.concurrent.Executors.newSingleThreadExecutor(runnable -> {
                            Thread thread = new Thread(runnable, "TauSync-ConnectAttempt");
                            thread.setDaemon(true);
                            return thread;
                        });
                try {
                    java.util.concurrent.Future<?> connectFuture = connectRunner.submit(() -> {
                        if (hybrid) {
                            tauSync.connectHybrid(
                                    applicationContext,
                                    currentRemoteDevice.getMacAddress(),
                                    BT_CONNECT_INNER_TIMEOUT_SECONDS);
                        } else {
                            tauSync.connectTo(currentRemoteDevice.getPcIp(), 4);
                        }
                    });
                    awaitConnectResult(connectFuture, hybrid, outerTimeoutSeconds);
                } finally {
                    // One-shot executor: without this shutdown its worker thread lives for the
                    // rest of the process, leaking one thread per connection attempt.
                    connectRunner.shutdown();
                }

                // connect success
                Log.d(TAG, "🟢 connect returned successfully (hybrid=" + hybrid + ")");

                persistentReconnect = false;
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
     * Waits for the in-flight connect task. The base wait covers a normal connect + handshake;
     * when it elapses while the PC operator's approval dialog is open (the server announced
     * APPROVAL_PENDING over Bluetooth), the wait is extended once so a slow approval cannot abort
     * a connection the PC is about to accept. Any abort tears the attempt down immediately via
     * {@link #abortConnectAttempt} — an abandoned handshake must never keep a live Bluetooth
     * socket behind (the "zombie session" the PC could later complete a connection with).
     */
    private void awaitConnectResult(java.util.concurrent.Future<?> connectFuture,
                                    boolean hybrid,
                                    int baseTimeoutSeconds) throws Exception {
        try {
            connectFuture.get(baseTimeoutSeconds, java.util.concurrent.TimeUnit.SECONDS);
            return;
        } catch (java.util.concurrent.TimeoutException e) {
            if (!(hybrid && TauSync.isApprovalPending())) {
                abortConnectAttempt(connectFuture);
                throw new Exception("Connection timed out after " + baseTimeoutSeconds + " seconds");
            }
        }

        Log.i(TAG, "PC approval in progress — extending connect wait by "
                + APPROVAL_WAIT_EXTENSION_SECONDS + "s");
        try {
            connectFuture.get(APPROVAL_WAIT_EXTENSION_SECONDS, java.util.concurrent.TimeUnit.SECONDS);
        } catch (java.util.concurrent.TimeoutException e) {
            abortConnectAttempt(connectFuture);
            throw new Exception("Connection timed out waiting for approval on the PC");
        }
    }

    /**
     * Cancels an abandoned connect attempt and disconnects its TauSync instance right away, so
     * the RFCOMM socket, receive loop, and session-control listener are gone before the next
     * attempt (or the PC operator's late decision) can reach them.
     */
    private void abortConnectAttempt(java.util.concurrent.Future<?> connectFuture) {
        connectFuture.cancel(true);
        TauSync abandoned = tauSync;
        tauSync = null;
        if (abandoned != null) {
            try {
                abandoned.disconnect();
            } catch (Exception ignored) {
            }
        }
    }

    /**
     * Handles connection failure and decides whether to retry.
     * Implements exponential backoff with jitter.
     */
    private void handleConnectionFailure(Exception error) {
        if (com.example.tausync_lib.implementations.management.ConnectionDeclinedException
                .isDeclined(error)) {
            // The PC operator explicitly declined — retrying would only re-prompt them with the
            // same request. Surface the failure and stop.
            Log.w(TAG, "Connection declined on the PC — not retrying.");
            persistentReconnect = false;
            updateStatus(TransportStatus.FAILED);
            if (listener != null) {
                mainHandler.post(() -> listener.onConnectionError(error));
            }
            return;
        }

        if (persistentReconnect) {
            // Recovering a lost session: never give up, just keep the capped back-off going.
            // Explicit disconnect/shutdown clears the flag and removes the queued retry.
            long jitterMs = (long) (Math.random() * 1000);
            long delayMs = nextRetryDelayMs + jitterMs;
            Log.i(TAG, "Reconnect attempt failed — retrying in " + delayMs + "ms");
            updateStatus(TransportStatus.RECONNECTING);
            mainHandler.postDelayed(retryConnectionRunnable, delayMs);
            nextRetryDelayMs = Math.min(nextRetryDelayMs * 2, MAX_RETRY_DELAY_MS);
            return;
        }

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
     * Starts the adaptive polling chain that checks for peer requests: fast
     * ({@link #POLLING_INTERVAL_MS}) while requests are flowing, backing off to
     * {@link #POLLING_IDLE_INTERVAL_MS} once the link has been quiet for
     * {@link #POLLING_ACTIVE_WINDOW_MS}. Each tick schedules the next one; the chain ends when the
     * transport leaves CONNECTED and a fresh chain (new generation) starts on the next connect.
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

        connectionLostSince[0] = 0L; // fresh health window for this session
<<<<<<< HEAD
        pollingExecutor.scheduleWithFixedDelay(() -> {
            // tauSync may be null during the reconnect window (handlePollingFailure
            // has already cleared it before attemptConnection creates the new instance).
            if (isShuttingDown.get() || status != TransportStatus.CONNECTED || tauSync == null) {
                return;
            }

            // Connection-health watchdog. getPeerWaitingWords() is a discovery snapshot that does
            // NOT throw on a dropped socket, so it can't detect a vanished PC by itself; isConnected()
            // can. evaluateHealth() applies the grace window so a transient blip (transport
            // reconnects) is tolerated and only a sustained loss is surfaced as a disconnect.
            switch (evaluateHealth(connectionLostSince, tauSync.isConnected(),
                    System.currentTimeMillis(), CONNECTION_LOST_GRACE_MS)) {
                case LOST:
                    handleConnectionLost();
                    return;
                case WITHIN_GRACE:
                    return;          // down but still inside the grace window — wait it out
                case HEALTHY:
                default:
                    break;           // fall through to the normal peer-request dispatch
            }

            try {
                List<String> waitingChannels = tauSync.getPeerWaitingWords();
                if (!waitingChannels.isEmpty() && listener != null) {
=======
        lastPeerRequestMs = System.currentTimeMillis(); // start fast — a request often follows connect
        int generation = pollGeneration.incrementAndGet();
        schedulePollTick(generation, POLLING_INTERVAL_MS);

        Log.d(TAG, "Started adaptive polling (fast=" + POLLING_INTERVAL_MS
                + "ms, idle=" + POLLING_IDLE_INTERVAL_MS + "ms)");
    }

    private void schedulePollTick(int generation, long delayMs) {
        ScheduledExecutorService executor = pollingExecutor;
        if (executor == null || executor.isShutdown()) {
            return;
        }
        try {
            executor.schedule(() -> pollTick(generation), delayMs, TimeUnit.MILLISECONDS);
        } catch (java.util.concurrent.RejectedExecutionException ignored) {
            // Executor shut down between the check and the schedule — the chain simply ends.
        }
    }

    private void pollTick(int generation) {
        if (generation != pollGeneration.get()) {
            return; // superseded by a newer polling session — never run two chains at once
        }
        // tauSync may be null during the reconnect window (handlePollingFailure has already
        // cleared it before attemptConnection creates the new instance). Ending the chain here is
        // safe: the next successful connect starts a fresh one.
        if (isShuttingDown.get() || status != TransportStatus.CONNECTED || tauSync == null) {
            return;
        }

        // Connection-health watchdog. getPeerWaitingWords() is a discovery snapshot that does
        // NOT throw on a dropped socket, so it can't detect a vanished PC by itself; isConnected()
        // can. evaluateHealth() applies the grace window so a transient blip is tolerated and only
        // a sustained loss triggers the automatic reconnection.
        switch (evaluateHealth(connectionLostSince, tauSync.isConnected(),
                System.currentTimeMillis(), CONNECTION_LOST_GRACE_MS)) {
            case LOST:
                handleConnectionLost();
                return;
            case WITHIN_GRACE:
                // Down but inside the grace window — keep watching at the fast interval so the
                // loss (or recovery) is noticed promptly.
                schedulePollTick(generation, POLLING_INTERVAL_MS);
                return;
            case HEALTHY:
            default:
                break; // fall through to the normal peer-request dispatch
        }

        try {
            List<String> waitingChannels = tauSync.getPeerWaitingWords();
            if (!waitingChannels.isEmpty()) {
                lastPeerRequestMs = System.currentTimeMillis();
                if (listener != null) {
>>>>>>> main
                    mainHandler.post(() -> listener.onPeerRequestsAvailable(waitingChannels));
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "Error polling for peer requests: " + e.getMessage());
            // Treat polling error as connection failure - initiate reconnect
            handlePollingFailure(e);
            return;
        }

        boolean active = System.currentTimeMillis() - lastPeerRequestMs <= POLLING_ACTIVE_WINDOW_MS;
        schedulePollTick(generation, active ? POLLING_INTERVAL_MS : POLLING_IDLE_INTERVAL_MS);
    }

    /** Outcome of a single connection-health evaluation in the poll loop. */
    enum Health { HEALTHY, WITHIN_GRACE, LOST }

    /**
     * Pure decision for the poll-loop health watchdog (static + package-private so it is unit
     * testable without constructing the manager).
     *
     * <p>Reads/updates {@code lostSince[0]} (0 = healthy, else epoch-ms of the first down tick)
     * and classifies the link:
     * <ul>
     *   <li>{@code isConnected} → {@link Health#HEALTHY}; the down-marker is cleared.</li>
     *   <li>first down tick → records {@code nowMs} and returns {@link Health#WITHIN_GRACE}.</li>
     *   <li>still down but {@code < graceMs} elapsed → {@link Health#WITHIN_GRACE}.</li>
     *   <li>down for {@code >= graceMs} → {@link Health#LOST}.</li>
     * </ul>
     * Called only on the single polling-executor thread, so the marker needs no locking.
     * (A real {@code System.currentTimeMillis()} is never 0, so the 0-sentinel never collides.)
     */
    static Health evaluateHealth(long[] lostSince, boolean isConnected, long nowMs, long graceMs) {
        if (isConnected) {
            lostSince[0] = 0L;
            return Health.HEALTHY;
        }
        if (lostSince[0] == 0L) {
            lostSince[0] = nowMs;
            return Health.WITHIN_GRACE;
        }
        return (nowMs - lostSince[0] >= graceMs) ? Health.LOST : Health.WITHIN_GRACE;
    }

    /**
     * Handles a true (unclean) connection loss exactly once — by recovering it, not by tearing the
     * session down. The PC re-listens automatically after a drop and silently re-approves known
     * phones, so redialing here re-converges the two ends with zero user involvement.
     */
    private void handleConnectionLost() {
        if (isShuttingDown.get() || status != TransportStatus.CONNECTED) {
            return;
        }
        Log.w(TAG, "Connection lost (down >= grace window) — starting automatic reconnection");
        beginPersistentReconnect();
    }

    /**
     * Recovers an unexpectedly lost session without user involvement: redials the saved device
     * with exponential back-off (capped at {@link #MAX_RETRY_DELAY_MS}) until it succeeds or an
     * explicit disconnect/shutdown stops it. The dead TauSync instance is closed by
     * {@code attemptConnection}'s previous-instance cleanup.
     *
     * <p>Runs on the polling thread — the polling executor is stopped with the non-blocking
     * {@code shutdownNow()} ({@link #stopPolling()}'s awaitTermination would self-deadlock here);
     * the successful reconnect starts a fresh polling chain.
     */
    private void beginPersistentReconnect() {
        persistentReconnect = true;
        currentRetryAttempt = 0;
        nextRetryDelayMs = INITIAL_RETRY_DELAY_MS;
        updateStatus(TransportStatus.RECONNECTING);
        if (pollingExecutor != null && !pollingExecutor.isShutdown()) {
            pollingExecutor.shutdownNow();
        }
        attemptConnection();
    }

    /** Outcome of a single connection-health evaluation in the poll loop. */
    enum Health { HEALTHY, WITHIN_GRACE, LOST }

    /**
     * Pure decision for the poll-loop health watchdog (static + package-private so it is unit
     * testable without constructing the manager).
     *
     * <p>Reads/updates {@code lostSince[0]} (0 = healthy, else epoch-ms of the first down tick)
     * and classifies the link:
     * <ul>
     *   <li>{@code isConnected} → {@link Health#HEALTHY}; the down-marker is cleared.</li>
     *   <li>first down tick → records {@code nowMs} and returns {@link Health#WITHIN_GRACE}.</li>
     *   <li>still down but {@code < graceMs} elapsed → {@link Health#WITHIN_GRACE}.</li>
     *   <li>down for {@code >= graceMs} → {@link Health#LOST}.</li>
     * </ul>
     * Called only on the single polling-executor thread, so the marker needs no locking.
     * (A real {@code System.currentTimeMillis()} is never 0, so the 0-sentinel never collides.)
     */
    static Health evaluateHealth(long[] lostSince, boolean isConnected, long nowMs, long graceMs) {
        if (isConnected) {
            lostSince[0] = 0L;
            return Health.HEALTHY;
        }
        if (lostSince[0] == 0L) {
            lostSince[0] = nowMs;
            return Health.WITHIN_GRACE;
        }
        return (nowMs - lostSince[0] >= graceMs) ? Health.LOST : Health.WITHIN_GRACE;
    }

    /**
     * Surfaces a true (unclean) connection loss exactly once.
     *
     * <p>Flips the status to {@link TransportStatus#DISCONNECTING} so the next 20 ms tick
     * early-returns (no second fire), then hands off on the main thread to the listener, which
     * runs the same {@code cleanup()} the clean {@code DISCONNECT_FROM_PC} path uses. We do NOT
     * call {@link #stopPolling()} here — that blocks on {@code awaitTermination} and self-deadlocks
     * when invoked from inside a polling task; {@code cleanup() → shutdown() → disconnect()} stops
     * the poller from the main thread instead.
     */
    private void handleConnectionLost() {
        if (isShuttingDown.get() || status != TransportStatus.CONNECTED) {
            return;
        }
        Log.w(TAG, "Connection lost (down >= grace window) — surfacing disconnect");
        updateStatus(TransportStatus.DISCONNECTING);
        if (listener != null) {
            mainHandler.post(listener::onConnectionLost);
        }
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

        // Recover only if we were actively connected AND a deliberate shutdown is not already in
        // progress. isShuttingDown is set at the top of shutdown() (called by cleanup() from
        // DisconnectChannelHandler / sendDisconnectToPC), and prepareForDisconnect() flips the
        // status to DISCONNECTING before the farewell write — so a polling failure racing a
        // deliberate teardown can never trigger an unwanted reconnect (the old "auto send
        // connect_to_pc" bug).
        if (status == TransportStatus.CONNECTED && !isShuttingDown.get()) {
            beginPersistentReconnect();
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
        persistentReconnect = false;
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

    // Buffer for OUTGOING streams — matches the library's bulk-transfer chunk size (256 KB) so
    // each write comfortably clears the hybrid Wi-Fi routing threshold.
    private static final int OUTGOING_STREAM_BUFFER_BYTES =
            com.example.tausync_lib.core.CoreConfig.LARGE_TRANSFER_CHUNK_SIZE;

    // Minimum bytes to accumulate before an outgoing mid-stream write. Hybrid routing picks the
    // transport per write by size: a partial chunk (≤ 64 KB − 1) rides Bluetooth while a full one
    // rides Wi-Fi. Streaming sources (pipes — e.g. the webcam feed — and slow files) often return
    // partial reads, so writing them straight through flaps the stream between transports, paying
    // a barrier round-trip per flap and saturating Bluetooth. Filling to at least this size keeps
    // every mid-stream write on the fast link; only the final (EOF) chunk may be smaller.
    private static final int WIFI_ROUTE_MIN_FILL =
            com.example.tausync_lib.core.CoreConfig.HYBRID_SMALL_THRESHOLD_BYTES + 1;

    /**
     * Reads from {@code in} until the buffer holds at least {@link #WIFI_ROUTE_MIN_FILL} bytes,
     * the buffer is full, or EOF. Returns the number of bytes read (0 only at immediate EOF).
     */
    private static int readAtLeast(java.io.InputStream in, byte[] buf) throws java.io.IOException {
        int total = 0;
        while (total < WIFI_ROUTE_MIN_FILL && total < buf.length) {
            int n = in.read(buf, total, buf.length - total);
            if (n < 0) break;
            total += n;
        }
        return total;
    }

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
            // Use Wi-Fi output — bulk streaming (webcam, backup) must not go over Bluetooth.
            java.io.OutputStream out = stream.getWifiOutputStream();
            byte[] buf = new byte[FILE_CHUNK_SIZE];
            int n;
            long totalBytes = 0;
            int chunkCount = 0;
            while ((n = readAtLeast(inputStream, buf)) > 0) {
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
            byte[] buf = new byte[OUTGOING_STREAM_BUFFER_BYTES];
            int n;
            long totalBytes = 0;
            int chunkCount = 0;
            while ((n = readAtLeast(inputStream, buf)) > 0) {
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
                byte[] buf = new byte[OUTGOING_STREAM_BUFFER_BYTES];
                int n;
                long totalBytes = 0;
                int chunkCount = 0;
                while ((n = readAtLeast(in, buf)) > 0) {
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

    @Override
    public void serveReadSession(String channel, RangeReader reader) throws Exception {
        if (tauSync == null || status != TransportStatus.CONNECTED) {
            throw new IllegalStateException(
                    "Cannot serve channel [" + channel + "]: Not connected");
        }
        try (com.example.tausync_lib.implementations.management.TauSyncStream stream =
                     tauSync.connect(channel, DEFAULT_WRITE_CONNECT_TIMEOUT_S)) {
            // First line establishes the file for the whole session (sent once by
            // the desktop's read_open op).
            String openLine = stream.readLine();
            if (openLine == null) {
                throw new java.io.EOFException(
                        "serveReadSession: peer closed before open header on ["
                                + channel + "]");
            }
            String path = new org.json.JSONObject(openLine).getString("path");
            Log.d(TAG, "serveReadSession [" + channel + "]: open path=" + path);

            java.io.OutputStream out = stream.getOutputStream();
            byte[] buf = new byte[FILE_CHUNK_SIZE];

            // Serve one {offset,length} request per iteration, reusing the same
            // channel (and the file opened by the reader) until the peer closes it
            // (read_close → EOF on readLine).
            String reqLine;
            while ((reqLine = stream.readLine()) != null) {
                org.json.JSONObject req = new org.json.JSONObject(reqLine);
                long offset = req.getLong("offset");
                int length = req.getInt("length");

                ReadResult result;
                try {
                    result = reader.openRange(path, offset, length);
                } catch (Exception e) {
                    Log.w(TAG, "serveReadSession [" + channel + "]: reader threw", e);
                    result = ReadResult.error("io_error");
                }

                if (!result.ok) {
                    // Header only; keep the session open so the peer can retry/seek.
                    stream.writeString("{\"ok\":false,\"error\":\"" + result.error + "\"}\n");
                    out.flush();
                    Log.d(TAG, "serveReadSession [" + channel + "]: error=" + result.error
                            + " off=" + offset + " len=" + length);
                    continue;
                }

                // Success: declare the exact byte count, then stream exactly that many.
                stream.writeString("{\"ok\":true,\"length\":" + result.length + "}\n");
                try (java.io.InputStream in = result.stream) {
                    long remaining = result.length;
                    while (remaining > 0) {
                        int want = (int) Math.min(buf.length, remaining);
                        int n = in.read(buf, 0, want);
                        if (n <= 0) break;  // file shrank under us → peer detects truncation
                        out.write(buf, 0, n);
                        remaining -= n;
                    }
                    out.flush();
                }
            }
            Log.d(TAG, "serveReadSession [" + channel + "]: session ended for " + path);
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
        persistentReconnect = false;
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


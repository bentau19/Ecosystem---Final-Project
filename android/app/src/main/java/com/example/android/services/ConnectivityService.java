package com.example.android.services;

import android.app.Notification;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.lifecycle.Lifecycle;
import androidx.lifecycle.Observer;
import androidx.lifecycle.ProcessLifecycleOwner;

import com.example.android.data.datasource.BackupDataSource;
import com.example.android.data.datasource.SystemDataSource;
import com.example.android.repositories.VirtualDriveRepository;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.BackupTransferStatus;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.domain.enums.SendFileStatus;
import com.example.android.domain.enums.ConnectionType;
import com.example.android.enums.DeviceInfoChannels;
import com.example.android.enums.FileTransferChannels;
import com.example.android.enums.SessionChannels;
import com.example.android.enums.BackupChannels;
import com.example.android.enums.VirtualDriveChannels;
import com.example.android.network.handlers.BackupControlChannelHandler;
import com.example.android.network.handlers.VirtualDriveChannelHandler;
import com.example.android.network.handlers.ChannelHandlerRegistry;
import com.example.android.network.handlers.DeviceInfoChannelHandler;
import com.example.android.domain.usecases.BackupTransferUseCase;
import com.example.android.domain.usecases.ReceiveFileUseCase;
import com.example.android.domain.usecases.RespondToFileTransferUseCase;
import com.example.android.domain.usecases.SendFileUseCase;
import com.example.android.domain.usecases.VirtualDriveUseCase;
import com.example.android.domain.usecases.WebcamStreamUseCase;
import com.example.android.repositories.BackupRepository;
import com.example.android.repositories.SendFileRepository;
import com.example.android.repositories.WebcamRepository;
import com.example.android.network.handlers.FileDataChannelHandler;
import com.example.android.network.handlers.FileMetadataChannelHandler;
import com.example.android.network.handlers.PCNameChannelHandler;
import com.example.android.network.handlers.DisconnectChannelHandler;
import com.example.android.repositories.ReceiveFileRepository;
import com.example.android.network.transport.TransportManager;
import com.example.android.network.transport.TransportStatus;
import com.example.android.network.transport.TauSyncTransportManager;
import com.example.android.repositories.DeviceRepository;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * ConnectivityService - Thin Orchestrator for managing remote PC connections.
 * This foreground service acts as a mediator between the Transport Layer (TauSync)
 * and the application state (DeviceRepository), managing the connection lifecycle
 * and persistent notifications.
 */
public class ConnectivityService extends Service implements TransportManager.TransportListener {

    private static final String TAG = "TauSyncFlow";

    // Core infrastructure components
    private TransportManager transportManager;
    private ChannelHandlerRegistry handlerRegistry;
    private SystemDataSource systemDataSource;
    private DeviceRepository deviceRepository;
    private AppNotificationManager notificationManager;

    // File transfer UseCases — initialized after transportManager is ready
    private RespondToFileTransferUseCase respondToFileTransferUseCase;
    private ReceiveFileUseCase receiveFileUseCase;
    private SendFileUseCase sendFileUseCase;
    private BackupTransferUseCase backupTransferUseCase;

    // Virtual drive UseCase — serves all WinFsp filesystem ops forwarded by the desktop
    private VirtualDriveUseCase virtualDriveUseCase;

    // PC-name handler. Driven proactively from onStatusChanged(CONNECTED) — Android pulls the
    // PC name (the desktop only answers on request), so this is NOT registered for reactive
    // peer-request dispatch. Kept as a field so the connect-time request can reuse its
    // read+apply logic.
    private PCNameChannelHandler pcNameHandler;
    private WebcamStreamUseCase webcamStreamUseCase;

    // Observer for outgoing file transfer notifications — kept so we can remove it in onDestroy
    private Observer<SendFileStatus> sendFileStatusObserver;

    // Observer for backup transfer progress notifications — kept for removal in onDestroy
    private Observer<BackupTransferStatus> backupTransferStatusObserver;

    // Observer for the per-file sent counter — drives the progress notification ticker.
    // Kept as a field so it can be removed in onDestroy; without this it leaks one
    // observer per ConnectivityService instance across reconnects.
    private Observer<Integer> transferSentObserver;

    // Observer for backup scan failures — kept for removal in onDestroy
    private Observer<com.example.android.domain.enums.BackupScanStatus> backupScanStatusObserver;

    // Channels currently being handled by a PeerRequestHandler thread. Prevents the
    // poll loop from spawning a second handler for the same channel while a prior
    // writeToChannel() call is still blocking inside tauSync.connect().
    private final Set<String> inProgressChannels = ConcurrentHashMap.newKeySet();

    // Upper bound on peer-request handler threads. Must be >= the desktop's pipe
    // pool (8) so that many concurrent reads (e.g. a video's parallel prefetch
    // windows) are not throttled, with headroom for device-info / metadata ops.
    private static final int PEER_REQUEST_MAX_THREADS = 12;

    // Bounded pool that runs peer-request handlers, replacing an unbounded
    // new-Thread-per-channel spawn. A SynchronousQueue + AbortPolicy means that
    // when all threads are busy a new dispatch is rejected (not queued); the
    // caller releases the channel claim and the 2 s poll re-dispatches it once a
    // worker frees. Threads are daemons so they never block process exit. Never
    // use CallerRunsPolicy here: the caller is the UI main thread.
    private final ExecutorService peerRequestExecutor = new ThreadPoolExecutor(
            2, PEER_REQUEST_MAX_THREADS, 30L, TimeUnit.SECONDS,
            new SynchronousQueue<>(),
            new ThreadFactory() {
                private final AtomicInteger counter = new AtomicInteger();

                @Override
                public Thread newThread(Runnable r) {
                    Thread t = new Thread(r, "VDPeerRequest-" + counter.incrementAndGet());
                    t.setDaemon(true);
                    return t;
                }
            });

    // Set to true at the very start of cleanup() so that any onStatusChanged(CONNECTED)
    // callbacks still sitting in the main-handler queue are silently discarded rather
    // than overwriting the DISCONNECTED postValue that cleanup() emits last.
    //
    // Scenario this guards against: a reconnect attempt queued by handlePollingFailure
    // (before the user tapped Disconnect) completes while cleanup() is blocking the
    // main thread inside transportManager.shutdown() → awaitTermination(). The
    // resulting onStatusChanged(CONNECTED) arrives in the queue AFTER
    // deviceRepository.disconnect() posts DISCONNECTED — but MutableLiveData.postValue
    // coalesces and delivers only the last value (CONNECTED), causing a spurious
    // auto-reconnect to ActionsFragment.
    private volatile boolean isCleaningUp = false;

    @Override
    public void onCreate() {
        super.onCreate();
        Log.d(TAG, "Service created");

        // Initialize notification management and start observing repository state changes
        notificationManager = new AppNotificationManager(this);
        notificationManager.startListeningToConnectionChanges();

        systemDataSource = new SystemDataSource(this);

        // Safely retrieve the Singleton Repository instance with a fallback mechanism
        // to circumvent eventual race conditions on Android 14+ startup sequences
        try {
            deviceRepository = DeviceRepository.getInstance();
        } catch (IllegalStateException e) {
            Log.w(TAG, "Repository not initialized, initializing with fallback data");
            deviceRepository = DeviceRepository.getInstance(
                    systemDataSource.getDeviceId(),
                    systemDataSource.getDeviceModel()
            );
        }

        transportManager = new TauSyncTransportManager();
        handlerRegistry = new ChannelHandlerRegistry();

        // Initialize file transfer UseCases before registering handlers —
        // FileDataChannelHandler takes a direct reference to receiveFileUseCase.
        respondToFileTransferUseCase = new RespondToFileTransferUseCase(transportManager);
        receiveFileUseCase = new ReceiveFileUseCase(transportManager, ReceiveFileRepository.getInstance(), this);
        sendFileUseCase = new SendFileUseCase(transportManager, SendFileRepository.getInstance(), this);
        backupTransferUseCase = new BackupTransferUseCase(
                transportManager, BackupRepository.getInstance(), this, new BackupDataSource());
        webcamStreamUseCase = new WebcamStreamUseCase(transportManager, WebcamRepository.getInstance());

        // Virtual drive — on-demand request→response; the DataSource answers each WinFsp op
        // directly from the filesystem (no background scan, no persistent index).
        virtualDriveUseCase = new VirtualDriveUseCase(transportManager, VirtualDriveRepository.getInstance());

        registerChannelHandlers();
        registerFileTransferActionListener();
        registerIncomingRequestListener();
        registerSendFileActionListener();
        registerSendFileStatusObserver();
        registerBackupTransferActionListener();
        registerBackupTransferProgressObserver();
        registerBackupScanStatusObserver();
        registerBackupControlActionListener();
        registerWebcamActionListener();

        Log.d(TAG, "Service initialization complete");
    }

    /**
     * Registers dedicated and generic channel handlers for decoupled message dispatching.
     */
    private void registerChannelHandlers() {
        Log.d(TAG, "Registering channel handlers using generic DeviceInfoChannelHandler...");

        // PC_NAME is a Setter (receives data and modifies local state). Android pulls it
        // proactively on connect — see requestPcName() — so it is intentionally NOT registered
        // for reactive peer-request dispatch: the desktop never opens this channel itself, it
        // only responds once Android opens it.
        pcNameHandler = new PCNameChannelHandler(deviceRepository, transportManager);

        // DISCONNECT_FROM_PC uses a specialized class to handle PC-initiated disconnects
        handlerRegistry.registerHandler(
                SessionChannels.DISCONNECT_FROM_PC.getValue(),
                new DisconnectChannelHandler(deviceRepository, transportManager, this::cleanup)
        );

        // FILE_METADATA_PC_TO_ANDROID handles incoming file transfer requests from the PC
        handlerRegistry.registerHandler(
                FileTransferChannels.REGULAR_FILE_METADATA_PC_TO_ANDROID.getValue(),
                new FileMetadataChannelHandler(transportManager, ReceiveFileRepository.getInstance())
        );

        // FILE_DATA_PC_TO_ANDROID receives the actual file bytes — triggered by the polling loop.
        // Desktop opens this channel only after receiving ACCEPT, so there is no simultaneous-connect
        handlerRegistry.registerHandler(
                FileTransferChannels.REGULAR_FILE_DATA_PC_TO_ANDROID.getValue(),
                new FileDataChannelHandler(receiveFileUseCase, ReceiveFileRepository.getInstance())
        );

        // BACKUP_CONTROL_FROM_PC — PC-initiated pause/resume/stop during an active backup session.
        // Registered once at startup; the UseCase's public methods guard against being called
        // outside an active session, so stray commands when no transfer is running are safe no-ops.
        handlerRegistry.registerHandler(
                BackupChannels.BACKUP_CONTROL_FROM_PC.getValue(),
                new BackupControlChannelHandler(transportManager, backupTransferUseCase)
        );

        // Virtual drive — one handler instance per op-type, registered under the prefix key
        // (base + "_", e.g. "virtual_drive_list_"). The ChannelHandlerRegistry prefix-fallback
        // routes each UUID-suffixed incoming channel (e.g. "virtual_drive_list_a1b2c3d4") to
        // the matching handler without any changes to the registry logic.
        for (VirtualDriveChannels vdCh : VirtualDriveChannels.values()) {
            handlerRegistry.registerHandler(
                    vdCh.getValue() + "_",                        // prefix key
                    new VirtualDriveChannelHandler(vdCh.getValue(), virtualDriveUseCase)
            );
        }

        // All other device telemetry data types are registered inline as Getters using generic Lambda functional interfaces
        registerDeviceInfoHandler(DeviceInfoChannels.NAME_FROM_ANDROID.getValue(), this::getDeviceName);
        registerDeviceInfoHandler(DeviceInfoChannels.OS_FROM_ANDROID.getValue(), this::getDeviceOs);
        registerDeviceInfoHandler(DeviceInfoChannels.ID.getValue(), this::getLocalDeviceIdValue);
        registerDeviceInfoHandler(DeviceInfoChannels.IP_FROM_ANDROID.getValue(), this::getDeviceIp);
        registerDeviceInfoHandler(DeviceInfoChannels.BATTERY_LEVEL_FROM_ANDROID.getValue(), this::getBatteryLevel);
        registerDeviceInfoHandler(DeviceInfoChannels.BATTERY_CHARGING_FROM_ANDROID.getValue(), this::getBatteryCharging);
        registerDeviceInfoHandler(DeviceInfoChannels.STORAGE_TOTAL_FROM_ANDROID.getValue(), this::getStorageTotal);
        registerDeviceInfoHandler(DeviceInfoChannels.STORAGE_USED_FROM_ANDROID.getValue(), this::getStorageUsed);

        Log.d(TAG, "Registered " + handlerRegistry.getHandlerCount() + " handlers");
    }

    /**
     * Structural helper to bind a data channel with a specific lambda implementation of ValueProvider.
     */
    private void registerDeviceInfoHandler(String channel, DeviceInfoChannelHandler.ValueProvider valueProvider) {
        handlerRegistry.registerHandler(
                channel,
                new DeviceInfoChannelHandler(channel, transportManager, valueProvider)
        );
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.d(TAG, "onStartCommand: Service starting");

        // Check if this is a disconnect request action
        if (intent != null && "com.example.android.ACTION_SEND_DISCONNECT".equals(intent.getAction())) {
            Log.d(TAG, "Received disconnect action, sending disconnect notification to PC");
            // Arm the cleanup guard on the main thread BEFORE spawning the background
            // disconnect thread. Any onStatusChanged(CONNECTED) posted by a racing
            // reconnect attempt (handlePollingFailure → connectTo()) lands in the
            // main-thread queue AFTER this frame returns — so isCleaningUp is already
            // true when that callback is processed and it is silently discarded.
            // Setting it here (vs. inside cleanup()) closes the window between
            // stopSelf() and onDestroy() where the flag would otherwise still be false.
            isCleaningUp = true;
            // Post DISCONNECTING immediately so the UI disables the button before the
            // background thread fires. The final DISCONNECTED post comes from cleanup().
            deviceRepository.updateConnectionStatus(ConnectionStatus.DISCONNECTING);
            sendDisconnectToPC();
            return START_NOT_STICKY;
        }

        // Backup transfer control actions from the sticky progress notification —
        // fire immediately, no confirmation, and don't disturb the connection lifecycle.
        if (intent != null && AppNotificationManager.ACTION_BACKUP_PAUSE.equals(intent.getAction())) {
            Log.d(TAG, "Received backup pause action");
            if (backupTransferUseCase != null) {
                backupTransferUseCase.pauseTransfer();
            }
            return START_NOT_STICKY;
        }
        if (intent != null && AppNotificationManager.ACTION_BACKUP_RESUME.equals(intent.getAction())) {
            Log.d(TAG, "Received backup resume action");
            if (backupTransferUseCase != null) {
                backupTransferUseCase.resumeTransfer();
            }
            return START_NOT_STICKY;
        }
        if (intent != null && AppNotificationManager.ACTION_BACKUP_STOP.equals(intent.getAction())) {
            Log.d(TAG, "Received backup stop action");
            if (backupTransferUseCase != null) {
                backupTransferUseCase.stopTransfer();
            }
            return START_NOT_STICKY;
        }

        // URI permission delegation + send trigger from ShareReceiverActivity.
        // By the time onStartCommand runs, Android has already registered the URI grant
        // for this service (FLAG_GRANT_READ_URI_PERMISSION on the incoming Intent).
        // Starting the send flow from here guarantees the grant is fully active before
        // any ContentResolver I/O runs in SendFileUseCase.
        if (intent != null && "com.example.android.ACTION_GRANT_FILE_URI".equals(intent.getAction())) {
            android.net.Uri fileUri = intent.getData();
            String fileName = intent.getStringExtra("FILE_NAME");
            Log.d(TAG, "URI grant received, starting send: " + fileName);
            if (fileUri != null && fileName != null) {
                SendFileRepository.getInstance().requestSend(fileUri, fileName);
            }
            return START_NOT_STICKY;
        }

        // Enforce immediate foreground promotion to fulfill Android's strict background execution policies
        Notification notification = notificationManager.buildNotification("Connecting to PC...");
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(AppNotificationManager.NOTIFICATION_ID, notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(AppNotificationManager.NOTIFICATION_ID, notification);
        }

        String targetIp = (intent != null) ? intent.getStringExtra("TARGET_IP") : null;
        Log.d(TAG, "Target IP: " + targetIp);

        if (targetIp == null) {
            Log.e(TAG, "No TARGET_IP provided, stopping service");
            stopSelf();
            return START_NOT_STICKY;
        }

        RemoteDeviceInfo remoteDevice = new RemoteDeviceInfo(
                "PC",
                targetIp,
                ConnectionType.WIFI
        );

        // Update the repository with the remote device info (initial state before handshake)
        deviceRepository.connect(remoteDevice.getPcName(), remoteDevice.getPcIp(), remoteDevice.getConnectionType());

        deviceRepository.updateConnectionStatus(ConnectionStatus.CONNECTING);
        transportManager.connect(remoteDevice, this);

        return START_STICKY;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        Log.d(TAG, "App removed from recents — sending disconnect before cleanup");
        // Same race as the ACTION_SEND_DISCONNECT path: arm isCleaningUp on the main
        // thread before any background work starts so reconnect callbacks are discarded.
        isCleaningUp = true;
        if (transportManager != null && transportManager.isConnected()) {
            // sendDisconnectToPC() opens the DISCONNECT_FROM_PHONE channel so
            // the desktop transitions cleanly instead of detecting a socket drop.
            // It calls stopSelf() in its finally block → onDestroy() → cleanup().
            sendDisconnectToPC();
        } else {
            cleanup();  // includes stopSelf()
        }
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        Log.d(TAG, "Service destroyed");
        if (notificationManager != null) {
            notificationManager.stopListeningToConnectionChanges();
        }
        if (sendFileStatusObserver != null) {
            SendFileRepository.getInstance().getSendStatus().removeObserver(sendFileStatusObserver);
        }
        if (backupTransferStatusObserver != null) {
            BackupRepository.getInstance().getTransferStatus().removeObserver(backupTransferStatusObserver);
        }
        if (transferSentObserver != null) {
            BackupRepository.getInstance().getTransferSent().removeObserver(transferSentObserver);
        }
        if (backupScanStatusObserver != null) {
            BackupRepository.getInstance().getScanStatus().removeObserver(backupScanStatusObserver);
        }
        cleanup();
        super.onDestroy();
    }

    /**
     * Gracefully releases open sockets, unregisters subcomponents, and resets the local connection state.
     */
    private void cleanup() {
        isCleaningUp = true;
        Log.d(TAG, "Cleanup started - stopping threads and shutting down network");
        if (handlerRegistry != null) {
            handlerRegistry.shutdownAll();
        }
        // Stop accepting peer-request handlers and interrupt in-flight ones; the
        // transportManager.shutdown() below closes the socket that unblocks any
        // handler parked in tauSync.connect().
        peerRequestExecutor.shutdownNow();
        if (transportManager != null) {
            transportManager.shutdown();
        }
        if (deviceRepository != null) {
            // Hard disconnect resets state models so the application re-opens directly on the connect screen
            deviceRepository.disconnect();
        }

        // Stop webcam stream if one is active
        if (webcamStreamUseCase != null) {
            webcamStreamUseCase.stop();
        }
        WebcamRepository.getInstance().reset();

        // Reset file transfer repositories so stale status isn't shown after reconnect
        ReceiveFileRepository.getInstance().reset();
        SendFileRepository.getInstance().reset();

        // Reset backup repository — clears any in-flight scan (scanActiveForTransfer=false)
        // so a scan that completes after reconnect does NOT auto-send the manifest on the
        // new connection session. Also clears stale transfer progress counters/status.
        BackupRepository.getInstance().reset();
        BackupRepository.getInstance().resetTransfer();

        // Remove the foreground notification so it doesn't stay in the status bar
        Log.d(TAG, "Removing foreground notification");
        stopForeground(Service.STOP_FOREGROUND_REMOVE);

        // Stop the service so it doesn't keep running in the background
        Log.d(TAG, "Stopping ConnectivityService");
        stopSelf();
    }

    // ============ TransportManager.TransportListener Implementation ============

    @Override
    public void onStatusChanged(TransportStatus status) {
        Log.d(TAG, "Transport status changed: " + status);

        // Discard any status update that arrives after cleanup() has started.
        // Both cleanup() and these onStatusChanged() callbacks run on the main thread,
        // so once isCleaningUp is set, no further callbacks can slip through.
        if (isCleaningUp) {
            Log.d(TAG, "Ignoring status update during cleanup: " + status);
            return;
        }

        // Map transport status to domain status
        ConnectionStatus connectionStatus = mapTransportStatusToConnectionStatus(status);

        // Guard: if the app has already reached FAILED, ignore any secondary status update.
        if (deviceRepository.getCurrentConnectionStatus() == ConnectionStatus.FAILED) {
            Log.w(TAG, "Connection already marked as FAILED. Ignoring secondary status: " + status);
            return;
        }

        if (status == TransportStatus.CONNECTED) {
            deviceRepository.updateConnectionStatus(ConnectionStatus.CONNECTED);
            requestPcName();
        } else if (status == TransportStatus.CONNECTING || status == TransportStatus.RECONNECTING) {
            deviceRepository.updateConnectionStatus(connectionStatus);
        } else if (status == TransportStatus.FAILED) {
            deviceRepository.updateConnectionStatus(ConnectionStatus.FAILED);
        }
    }

    /**
     * Proactively pulls the PC name on a background thread once the transport is connected.
     *
     * <p>Android initiates the {@code pc_name} channel (the desktop only answers on request via
     * its {@code PhoneRequestService} listener loop), so this read must be kicked off actively
     * rather than waiting for a peer request that never comes. {@code onStatusChanged} runs on
     * the main thread and {@link com.example.android.network.handlers.PCNameChannelHandler}'s
     * read blocks, hence the dedicated thread.
     *
     * <p>The channel is claimed in {@link #inProgressChannels} first so a re-fired
     * {@code CONNECTED} (e.g. a reconnect) cannot overlap an in-flight request; reconnects
     * legitimately re-fetch the name once the prior request has completed.
     */
    private void requestPcName() {
        String channel = DeviceInfoChannels.PC_NAME.getValue();
        if (!inProgressChannels.add(channel)) {
            Log.d(TAG, "PC name request already in progress, skipping");
            return;
        }
        new Thread(() -> {
            try {
                pcNameHandler.onPeerRequest();
            } finally {
                inProgressChannels.remove(channel);
            }
        }, "PcNameRequest").start();
    }

    @Override
    public void onPeerRequestsAvailable(java.util.List<String> channels) {
        Log.d(TAG, "Peer requests available for channels: " + channels);

        // Called on the main thread via mainHandler.post(). Each channel gets its own
        // daemon thread so device-info channels respond in parallel (matching the PC's
        // concurrent ThreadPoolExecutor reads). inProgressChannels prevents duplicate
        // dispatches: the poll loop fires every 2 s regardless of how long a handler
        // blocks inside writeToChannel(), so without this guard each poll tick would
        // spawn a new thread that collides with the still-running one and throws
        // IllegalStateException: "Connect already in progress for word '...'".
        for (String channel : channels) {
            // Backup channels below are consumed directly by BackupTransferUseCase
            // threads (readFromChannel / writeToChannel / streamInputStreamToChannel),
            // never via the registry — skip them to avoid spurious "No handler
            // registered" warnings. This includes backup_manifest, which the PC's
            // listener loop keeps pending almost continuously by design.
            // backup_ctrl_pc is NOT skipped: it has a real registered handler
            // (BackupControlChannelHandler).
            if (isDirectlyConsumedBackupChannel(channel)) continue;

            // Atomically claim the channel. If another thread is already inside
            // handlePeerRequest() for this word, skip — the poll will retry it next tick.
            if (!inProgressChannels.add(channel)) {
                Log.d(TAG, "Channel already in progress, skipping: " + channel);
                continue;
            }

            final String ch = channel;
            try {
                peerRequestExecutor.execute(() -> {
                    try {
                        handlerRegistry.handlePeerRequest(ch);
                    } finally {
                        inProgressChannels.remove(ch);
                    }
                });
            } catch (RejectedExecutionException rejected) {
                // Pool saturated: release the claim so the next poll tick re-dispatches
                // this channel once a worker frees. Never run inline — the caller is the
                // UI main thread and handlePeerRequest() blocks for the whole op.
                inProgressChannels.remove(ch);
                Log.d(TAG, "Peer-request pool saturated, deferring channel: " + ch);
            }
        }
    }

    /**
     * Returns {@code true} for backup channels that are consumed directly by
     * {@code BackupTransferUseCase} threads rather than dispatched through the
     * {@code ChannelHandlerRegistry}. These channels legitimately appear in the
     * peer-waiting list (the PC opens them and blocks until Android connects the same
     * word), so reporting "No handler registered" for them is pure noise — by design
     * no handler will ever exist.
     *
     * @param channel Full channel name from the peer-waiting snapshot.
     * @return {@code true} if the registry should not be consulted for this channel.
     */
    private static boolean isDirectlyConsumedBackupChannel(String channel) {
        return channel.startsWith(BackupChannels.BACKUP_FILE_RESULT.getValue())
                || channel.startsWith(BackupChannels.BACKUP_FILE_DATA_SLOT.getValue())
                || channel.startsWith(BackupChannels.BACKUP_FILE_META_SLOT.getValue())
                || channel.equals(BackupChannels.BACKUP_READY_FROM_PC.getValue())
                || channel.equals(BackupChannels.BACKUP_MANIFEST_FROM_ANDROID.getValue());
    }

    @Override
    public void onConnectionError(Exception error) {
        Log.e(TAG, "Connection error: " + error.getMessage(), error);
        deviceRepository.updateConnectionStatus(ConnectionStatus.FAILED);
        stopSelf();
    }

    @Override
    public void onReconnectAttempt(int attemptNumber, int maxRetries) {
        Log.i(TAG, "Reconnect attempt " + attemptNumber + "/" + maxRetries);
        deviceRepository.updateConnectionStatus(ConnectionStatus.RECONNECTING);
    }

    /**
     * Maps the internal, concrete transport statuses directly into the generic domain model ConnectionStatus.
     */
    private ConnectionStatus mapTransportStatusToConnectionStatus(TransportStatus transportStatus) {
        switch (transportStatus) {
            case CONNECTING:
                return ConnectionStatus.CONNECTING;
            case CONNECTED:
                return ConnectionStatus.CONNECTED;
            case RECONNECTING:
                return ConnectionStatus.RECONNECTING;
            case FAILED:
                return ConnectionStatus.FAILED;
            case IDLE:
            case DISCONNECTING:
            default:
                return ConnectionStatus.DISCONNECTED;
        }
    }

    /**
     * Sends a disconnect notification to the PC when the user initiates a disconnect on the phone.
     *
     * <p>Stops the polling loop first via {@link TransportManager#prepareForDisconnect()} to
     * prevent a race condition: the 20 ms polling tick calls {@code getPeerWaitingWords()} on the
     * same {@code TauSync} object that {@code writeToChannel} is about to block inside.  If the
     * poll fails concurrently it triggers {@code handlePollingFailure → tauSync.dispose()} which
     * kills the socket before the desktop can join the {@code disconnect_phone} meeting word.
     *
     * <p>A 3-second connect timeout is used instead of the default 30 s.  The desktop polls
     * every 200 ms and responds (via {@code tau.disconnect()}) within ~200 ms of detecting the
     * channel, so 3 s provides safe headroom while preventing a 30-second UI hang when the PC
     * is slow or unreachable.  The desktop's {@code tau.disconnect()} closes the TCP socket,
     * which causes {@code tauSync.connect()} here to throw — the exception is caught and cleanup
     * proceeds via the {@code finally} block regardless.
     *
     * <p>After the channel write (or on any exception) {@code stopSelf()} triggers
     * {@link #onDestroy()} → {@link #cleanup()}, which shuts down the transport and resets the
     * repository.
     */
    private void sendDisconnectToPC() {
        new Thread(() -> {
            try {
                if (transportManager != null && transportManager.isConnected()) {
                    // Stop the 20 ms polling loop BEFORE opening the channel.
                    // Without this, a concurrent polling tick calls getPeerWaitingWords()
                    // on the same TauSync object that writeToChannel is about to block inside.
                    // If that poll fails it triggers handlePollingFailure → tauSync.disconnect(),
                    // closing the socket underneath writeToChannel — writeToChannel throws and
                    // the PC never receives the disconnect channel (waits full 10 s timeout).
                    // prepareForDisconnect() sets status=DISCONNECTING (writeToChannel allows
                    // DISCONNECTING) and awaits any in-flight poll tick before returning.
                    transportManager.prepareForDisconnect();

                    // 10-second timeout: desktop detects the channel in ≤5 s (phone_request_service
                    // polls every 5 s). Caps worst-case disconnect latency instead of 30 s default.
                    transportManager.writeToChannel(
                            SessionChannels.DISCONNECT_FROM_PHONE.getValue(), "disconnect", 10);
                    Log.d(TAG, "Disconnect signal sent to PC");
                }
            } catch (Exception e) {
                Log.e(TAG, "Failed to send disconnect signal: " + e.getMessage());
            } finally {
                stopSelf();  // → onDestroy → cleanup → transportManager.shutdown + repository.disconnect
            }
        }).start();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        // Return null as this service is initialized exclusively via startService commands (Started Service),
        // decoupling UI layout instances from the core connectivity loop and communicating solely via the Repository layer.
        return null;
    }

    // ============ Generic Value Providers for Handlers (Telemetry Getters) ============

    private String getDeviceName() {
        return systemDataSource.getDeviceModel();
    }

    private String getDeviceOs() {
        return "Android " + Build.VERSION.RELEASE;
    }

    private String getLocalDeviceIdValue() {
        return systemDataSource.getDeviceId();
    }

    private String getDeviceIp() {
        return systemDataSource.getLocalIp();
    }

    private String getBatteryLevel() {
        return String.valueOf(systemDataSource.getBattery());
    }

    private String getBatteryCharging() {
        return String.valueOf(systemDataSource.isDeviceCharging());
    }

    private String getStorageTotal() {
        return String.valueOf(systemDataSource.getRawStorageStats().total());
    }

    private String getStorageUsed() {
        return String.valueOf(systemDataSource.getRawStorageStats().used());
    }

    // ============ File Transfer Action Listener ============

    /**
     * Observes SendFileRepository.getSendStatus() for the lifetime of this service.
     * Drives the send-progress notification directly — bypassing LiveData lifecycle
     * restrictions so notifications work even when no Activity is in the foreground.
     *
     * Must be called on the main thread (onCreate runs on main thread).
     */
    private void registerSendFileStatusObserver() {
        SendFileRepository repo = SendFileRepository.getInstance();
        sendFileStatusObserver = status -> {
            if (status == null) return;
            String fileName = repo.getCurrentFileName().getValue();
            String displayName = (fileName != null) ? fileName : "file";
            switch (status) {
                case WAITING_FOR_RESPONSE:
                    notificationManager.showSendFileProgressNotification(
                            "Waiting for PC to accept…  " + displayName);
                    break;
                case SENDING:
                    notificationManager.showSendFileProgressNotification(
                            "Sending " + displayName + "…");
                    break;
                case COMPLETED:
                    notificationManager.showSendFileResultNotification("File sent ✓", displayName);
                    repo.reset();
                    break;
                case REJECTED:
                    notificationManager.showSendFileResultNotification(
                            "Transfer rejected", "PC declined " + displayName);
                    repo.reset();
                    break;
                case FAILED:
                    notificationManager.showSendFileResultNotification(
                            "Transfer failed", "Could not send " + displayName);
                    repo.reset();
                    break;
                case IDLE:
                default:
                    break;
            }
        };
        repo.getSendStatus().observeForever(sendFileStatusObserver);
    }

    /**
     * Registers ConnectivityService as the SendFileActionListener on SendFileRepository.
     * When the user shares a file, the ViewModel calls repository.requestSend(uri),
     * which fires this listener on the main thread. We immediately spawn a dedicated
     * background thread so the blocking network I/O never touches the main thread.
     */
    private void registerSendFileActionListener() {
        SendFileRepository.getInstance().setActionListener(uri -> {
            new Thread(() -> {
                try {
                    sendFileUseCase.execute(uri);
                } catch (Exception e) {
                    Log.e(TAG, "Unexpected error in SendFileThread: " + e.getMessage());
                    SendFileRepository.getInstance().onSendFailed();
                }
            }, "SendFileThread").start();
        });
    }

    /**
     * Registers ConnectivityService as the IncomingRequestListener on the Repository.
     * This fires immediately when a transfer request arrives — bypassing LiveData's
     * lifecycle-awareness so the heads-up notification is shown even when the Activity
     * is paused/stopped (app in background).
     */
    private void registerIncomingRequestListener() {
        ReceiveFileRepository.getInstance().setIncomingRequestListener(request -> {
            Log.d(TAG, "Incoming request arrived: " + request.fileName());

            // Show a notification only when the app is in the background.
            // When the app is in the foreground, MainActivity's LiveData observer
            // handles the request by showing an in-app AlertDialog instead.
            boolean appInForeground = ProcessLifecycleOwner.get()
                    .getLifecycle()
                    .getCurrentState()
                    .isAtLeast(Lifecycle.State.STARTED);

            if (!appInForeground) {
                notificationManager.showFileTransferApprovalNotification(
                        request.fileName(),
                        request.getFormattedSize()
                );
            }
        });
    }

    // ============ Backup Transfer ============

    /**
     * Registers ConnectivityService as the {@link BackupRepository.TransferActionListener}.
     *
     * <p>When the scan completes and the ViewModel calls
     * {@link BackupRepository#requestTransfer}, this listener fires and spawns a
     * dedicated background thread that runs {@link BackupTransferUseCase#execute}.
     * Mirrors {@link #registerSendFileActionListener} exactly.
     */
    private void registerBackupTransferActionListener() {
        BackupRepository.getInstance().setTransferActionListener((files, options) -> {
            new Thread(() -> {
                try {
                    backupTransferUseCase.execute(files, options);
                } catch (Exception e) {
                    Log.e(TAG, "Unexpected error in BackupTransferThread: " + e.getMessage());
                    BackupRepository.getInstance().onTransferFailed();
                }
            }, "BackupTransferThread").start();
        });
    }

    /**
     * Observes {@link BackupRepository#getTransferStatus()} for the lifetime of this
     * service and drives the sticky progress notification.
     *
     * <p>Mirrors {@link #registerSendFileStatusObserver} — must be called on the main
     * thread (onCreate runs on main thread) because LiveData.observeForever requires it.
     */
    private void registerBackupTransferProgressObserver() {
        BackupRepository repo = BackupRepository.getInstance();
        backupTransferStatusObserver = status -> {
            if (status == null) return;

            switch (status) {
                case SENDING: {
                    // Read the current progress values from the LiveData
                    Integer sent  = repo.getTransferSent().getValue();
                    Integer total = repo.getTransferTotal().getValue();
                    int s = (sent  != null) ? sent  : 0;
                    int t = (total != null) ? total : 0;
                    notificationManager.showBackupProgressNotification(s, t);
                    break;
                }
                case PAUSED: {
                    Integer sent  = repo.getTransferSent().getValue();
                    Integer total = repo.getTransferTotal().getValue();
                    int s = (sent  != null) ? sent  : 0;
                    int t = (total != null) ? total : 0;
                    notificationManager.showBackupPausedNotification(s, t);
                    break;
                }
                case COMPLETED: {
                    Integer total  = repo.getTransferTotal().getValue();
                    Integer failed = repo.getFailedCount().getValue();
                    int t = (total  != null) ? total  : 0;
                    int f = (failed != null) ? failed : 0;
                    int succeeded = Math.max(0, t - f);
                    // One-time success/error summary — replaces the sticky progress
                    // notification (same BACKUP_PROGRESS_NOTIFICATION_ID).
                    notificationManager.showBackupCompleteNotification(succeeded, f);
                    // BackupFragment is no longer on screen to acknowledge this state —
                    // reset the repository here so the next backup starts cleanly.
                    repo.resetTransfer();
                    break;
                }
                case STOPPED:
                    // User tapped Stop in the notification — replace the sticky
                    // progress notification with a brief "Backup stopped" notice.
                    notificationManager.showBackupStoppedNotification();
                    repo.resetTransfer();
                    break;
                case CANCELED_BY_PC:
                    // PC dismissed the folder picker before any file was sent.
                    // BackupFragment is still on-screen and shows a Toast — no
                    // notification banner needed; just dismiss the progress icon.
                    notificationManager.dismissBackupProgressNotification();
                    repo.resetTransfer();
                    break;
                case FAILED:
                    // BackupFragment is gone — replace the sticky notification with a
                    // brief "Backup failed" notice instead of dismissing silently.
                    notificationManager.showBackupFailedNotification();
                    repo.resetTransfer();
                    break;
                case IDLE:
                default:
                    break;
            }
        };
        repo.getTransferStatus().observeForever(backupTransferStatusObserver);

        // Also observe transferSent so the notification counter ticks on every file.
        // Skip the final tick (sent == total): the COMPLETED transition that follows
        // immediately after replaces this notification with the one-time success/error
        // summary, so rendering "X / X files" here would only flicker or get stuck.
        // Stored in transferSentObserver so it is removed in onDestroy — without this
        // each service instance leaks one anonymous observer per reconnect.
        transferSentObserver = sent -> {
            Integer total = repo.getTransferTotal().getValue();
            int s = (sent  != null) ? sent  : 0;
            int t = (total != null) ? total : 0;
            if (BackupTransferStatus.SENDING.equals(
                    repo.getTransferStatus().getValue()) && s < t) {
                notificationManager.showBackupProgressNotification(s, t);
            }
        };
        repo.getTransferSent().observeForever(transferSentObserver);
    }

    /**
     * Observes {@link BackupRepository#getScanStatus()} for the lifetime of this
     * service so that scan failures (e.g. permission errors while enumerating
     * files) surface to the user even though {@code BackupFragment} has already
     * returned to the dashboard by the time the scan finishes.
     *
     * <p>Mirrors {@link #registerBackupTransferProgressObserver} — must be called
     * on the main thread (onCreate runs on main thread) because
     * {@code LiveData.observeForever} requires it.
     */
    private void registerBackupScanStatusObserver() {
        BackupRepository repo = BackupRepository.getInstance();
        backupScanStatusObserver = status -> {
            if (status == null) return;

            if (status == com.example.android.domain.enums.BackupScanStatus.FAILED) {
                notificationManager.showBackupScanFailedNotification();
                repo.reset();
            }
        };
        repo.getScanStatus().observeForever(backupScanStatusObserver);
    }

    /**
     * Registers ConnectivityService as the {@link BackupRepository.ControlActionListener}.
     *
     * <p>{@code BackupTransferUseCase} is only accessible here (in the service), so
     * pause/resume/stop requests originating from the in-app UI (BackupViewModel) or
     * from the sticky notification actions are routed through this listener to reach
     * the running use case on its background thread.
     */
    private void registerBackupControlActionListener() {
        BackupRepository.getInstance().setControlActionListener(
                new BackupRepository.ControlActionListener() {
                    @Override
                    public void onPauseRequested() {
                        if (backupTransferUseCase != null) {
                            backupTransferUseCase.pauseTransfer();
                        }
                    }

                    @Override
                    public void onResumeRequested() {
                        if (backupTransferUseCase != null) {
                            backupTransferUseCase.resumeTransfer();
                        }
                    }

                    @Override
                    public void onStopRequested() {
                        if (backupTransferUseCase != null) {
                            backupTransferUseCase.stopTransfer();
                        }
                    }
                }
        );
    }

    /**
     * Registers ConnectivityService as the {@link WebcamRepository.StreamActionListener}.
     * Mirrors registerBackupTransferActionListener — spawns a background thread on Start,
     * and calls stop() on the use case on Stop.
     */
    private void registerWebcamActionListener() {
        WebcamRepository.getInstance().setActionListener(new WebcamRepository.StreamActionListener() {
            @Override
            public void onStartRequested() {
                new Thread(() -> {
                    try {
                        webcamStreamUseCase.execute();
                    } catch (Exception e) {
                        Log.e(TAG, "Unexpected error in WebcamStreamThread: " + e.getMessage());
                        WebcamRepository.getInstance().onStreamFailed();
                    }
                }, "WebcamStreamThread").start();
            }

            @Override
            public void onStopRequested() {
                webcamStreamUseCase.stop();
            }
        });
    }

    /**
     * Registers ConnectivityService as the FileTransferActionListener on the Repository.
     * This is the bridge between the user's Accept/Reject decision (ViewModel/UI layer)
     * and the actual network operations (Transport layer).
     *
     * The listener runs on a dedicated background thread to avoid blocking the main thread.
     */
    private void registerFileTransferActionListener() {
        ReceiveFileRepository.getInstance().setActionListener(
                new ReceiveFileRepository.ReceiveFileActionListener() {

                    @Override
                    public void onUserAccepted(String fileName) {
                        new Thread(() -> {
                            try {
                                // Tell the PC we accept.
                                // We do NOT call receiveFileUseCase.execute() here anymore.
                                // Desktop will open file_data_pc after receiving ACCEPT,
                                // and the polling loop will trigger FileDataChannelHandler,
                                // which calls receiveFileUseCase — eliminating the race condition.
                                respondToFileTransferUseCase.accept();
                            } catch (Exception e) {
                                Log.e(TAG, "Error sending accept to PC: " + e.getMessage());
                                ReceiveFileRepository.getInstance().onTransferFailed();
                            } finally {
                                // Dismiss the approval notification — it has served its purpose.
                                notificationManager.dismissFileTransferNotification();
                            }
                        }, "FileTransferAcceptThread").start();
                    }

                    @Override
                    public void onUserRejected() {
                        new Thread(() -> {
                            try {
                                respondToFileTransferUseCase.reject();
                            } catch (Exception e) {
                                Log.e(TAG, "Error sending reject to PC: " + e.getMessage());
                            } finally {
                                notificationManager.dismissFileTransferNotification();
                            }
                        }, "FileTransferRejectThread").start();
                    }
                }
        );
    }
}
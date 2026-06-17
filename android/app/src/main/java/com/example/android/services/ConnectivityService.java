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

import com.example.android.data.datasource.SystemDataSource;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.BackupTransferStatus;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.domain.enums.SendFileStatus;
import com.example.android.domain.enums.ConnectionType;
import com.example.android.enums.Channel;
import com.example.android.enums.DeviceInfoChannels;
import com.example.android.enums.FileTransferChannels;
import com.example.android.enums.SessionChannels;
import com.example.android.network.handlers.ChannelHandlerRegistry;
import com.example.android.network.handlers.DeviceInfoChannelHandler;
import com.example.android.domain.usecases.BackupTransferUseCase;
import com.example.android.domain.usecases.ClipboardSyncUseCase;
import com.example.android.domain.usecases.ReceiveFileUseCase;
import com.example.android.domain.usecases.RespondToFileTransferUseCase;
import com.example.android.domain.usecases.SendFileUseCase;
import com.example.android.repositories.BackupRepository;
import com.example.android.repositories.SendFileRepository;
import com.example.android.network.handlers.ClipboardFromPCHandler;
import com.example.android.network.handlers.FileDataChannelHandler;
import com.example.android.network.handlers.FileMetadataChannelHandler;
import com.example.android.network.handlers.PCNameChannelHandler;
import com.example.android.network.handlers.DisconnectChannelHandler;
import com.example.android.repositories.ReceiveFileRepository;
import com.example.android.network.transport.TransportManager;
import com.example.android.network.transport.TransportStatus;
import com.example.android.network.transport.TauSyncTransportManager;
import com.example.android.repositories.DeviceRepository;

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
    private ClipboardSyncUseCase clipboardSyncUseCase;

    // Observer for outgoing file transfer notifications — kept so we can remove it in onDestroy
    private Observer<SendFileStatus> sendFileStatusObserver;

    // Observer for backup transfer progress notifications — kept for removal in onDestroy
    private Observer<BackupTransferStatus> backupTransferStatusObserver;

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
        backupTransferUseCase = new BackupTransferUseCase(transportManager, BackupRepository.getInstance(), this);
        clipboardSyncUseCase = new ClipboardSyncUseCase(transportManager, this);

        registerChannelHandlers();
        registerFileTransferActionListener();
        registerIncomingRequestListener();
        registerSendFileActionListener();
        registerSendFileStatusObserver();
        registerBackupTransferActionListener();
        registerBackupTransferProgressObserver();

        Log.d(TAG, "Service initialization complete");
    }

    /**
     * Registers dedicated and generic channel handlers for decoupled message dispatching.
     */
    private void registerChannelHandlers() {
        Log.d(TAG, "Registering channel handlers using generic DeviceInfoChannelHandler...");

        // PC_NAME uses a specialized class because it acts as a Setter (receives data and modifies local state)
        handlerRegistry.registerHandler(
                DeviceInfoChannels.PC_NAME.getValue(),
                new PCNameChannelHandler(deviceRepository, transportManager)
        );

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

        // CLIPBOARD_PC_TO_ANDROID receives clipboard text pushed automatically by the Desktop
        // whenever its QClipboard changes.  Writing to ClipboardManager is always allowed on
        // Android — no foreground restriction — so this works even when the app is in the background.
        handlerRegistry.registerHandler(
                com.example.android.enums.ClipboardChannels.CLIPBOARD_PC_TO_ANDROID.getValue(),
                new ClipboardFromPCHandler(transportManager, this)
        );

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
            // Post DISCONNECTING immediately so the UI disables the button before the
            // background thread fires. The final DISCONNECTED post comes from cleanup().
            deviceRepository.updateConnectionStatus(ConnectionStatus.DISCONNECTING);
            sendDisconnectToPC();
            return START_NOT_STICKY;
        }

        // URI permission delegation + send trigger from ShareReceiverActivity.
        // By the time onStartCommand runs, Android has already registered the URI grant
        // for this service (FLAG_GRANT_READ_URI_PERMISSION on the incoming Intent).
        // Starting the send flow from here guarantees the grant is fully active before
        // any ContentResolver I/O runs in SendFileUseCase.
        if (intent != null && "com.example.android.ACTION_SEND_CLIPBOARD".equals(intent.getAction())) {
            Log.d(TAG, "Received clipboard send action");
            new Thread(() -> clipboardSyncUseCase.execute(), "ClipboardSync").start();
            return START_NOT_STICKY;
        }

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
        Log.d(TAG, "App removed from recent apps, shutting down");
        cleanup();
        stopSelf();
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
        cleanup();
        super.onDestroy();
    }

    /**
     * Gracefully releases open sockets, unregisters sub-components, and resets the local connection state.
     */
    private void cleanup() {
        Log.d(TAG, "Cleanup started - stopping threads and shutting down network");
        if (handlerRegistry != null) {
            handlerRegistry.shutdownAll();
        }
        if (transportManager != null) {
            transportManager.shutdown();
        }
        if (deviceRepository != null) {
            // Hard disconnect resets state models so the application re-opens directly on the connect screen
            deviceRepository.disconnect();
        }

        // Reset file transfer repositories so stale status isn't shown after reconnect
        ReceiveFileRepository.getInstance().reset();
        SendFileRepository.getInstance().reset();

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

        // Map transport status to domain status
        ConnectionStatus connectionStatus = mapTransportStatusToConnectionStatus(status);

        // ◄ הגנה: אם המצב הנוכחי באפליקציה הוא כבר FAILED, אל תיתן לשום סטטוס משני לדרוס אותו
        if (deviceRepository.getCurrentConnectionStatus() == ConnectionStatus.FAILED) {
            Log.w(TAG, "Connection already marked as FAILED. Ignoring secondary status: " + status);
            return;
        }

        if (status == TransportStatus.CONNECTED) {
            deviceRepository.updateConnectionStatus(ConnectionStatus.CONNECTED);
        } else if (status == TransportStatus.CONNECTING || status == TransportStatus.RECONNECTING) {
            deviceRepository.updateConnectionStatus(connectionStatus);
        } else if (status == TransportStatus.FAILED) {
            deviceRepository.updateConnectionStatus(ConnectionStatus.FAILED);
        }
    }

    @Override
    public void onPeerRequestsAvailable(java.util.List<String> channels) {
        Log.d(TAG, "Peer requests available for channels: " + channels);

        // Handle sequential polling requests from the desktop server on a dedicated worker thread to maintain thread safety
        new Thread(() -> {
            for (String channel : channels) {
                handlerRegistry.handlePeerRequest(channel);
            }
        }, "PeerRequestHandlerThread").start();
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
     * <p>Writes to the {@code DISCONNECT_FROM_PHONE} TauSync channel, then stops this service.
     * {@code stopSelf()} triggers {@link #onDestroy()} → {@link #cleanup()}, which shuts down
     * the transport and resets the repository — no explicit sleep is needed because
     * {@code writeToChannel} closes the stream (and flushes data) before returning.
     */
    private void sendDisconnectToPC() {
        new Thread(() -> {
            try {
                if (transportManager != null && transportManager.isConnected()) {
                    transportManager.writeToChannel(
                            SessionChannels.DISCONNECT_FROM_PHONE.getValue(), "disconnect");
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
        return String.valueOf(systemDataSource.getRawStorageStats().getTotal());
    }

    private String getStorageUsed() {
        return String.valueOf(systemDataSource.getRawStorageStats().getUsed());
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
            Log.d(TAG, "Incoming request arrived: " + request.getFileName());

            // Show a notification only when the app is in the background.
            // When the app is in the foreground, MainActivity's LiveData observer
            // handles the request by showing an in-app AlertDialog instead.
            boolean appInForeground = ProcessLifecycleOwner.get()
                    .getLifecycle()
                    .getCurrentState()
                    .isAtLeast(Lifecycle.State.STARTED);

            if (!appInForeground) {
                notificationManager.showFileTransferApprovalNotification(
                        request.getFileName(),
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
        BackupRepository.getInstance().setTransferActionListener(files -> {
            new Thread(() -> {
                try {
                    backupTransferUseCase.execute(files);
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
                case COMPLETED: {
                    Integer total = repo.getTransferTotal().getValue();
                    int t = (total != null) ? total : 0;
                    notificationManager.showBackupCompleteNotification(t);
                    break;
                }
                case FAILED:
                    // Dismiss silently — BackupFragment will show an in-app error Toast
                    notificationManager.dismissBackupProgressNotification();
                    break;
                case IDLE:
                default:
                    break;
            }
        };
        repo.getTransferStatus().observeForever(backupTransferStatusObserver);

        // Also observe transferSent so the notification counter ticks on every file
        repo.getTransferSent().observeForever(sent -> {
            if (BackupTransferStatus.SENDING.equals(
                    repo.getTransferStatus().getValue())) {
                Integer total = repo.getTransferTotal().getValue();
                int s = (sent  != null) ? sent  : 0;
                int t = (total != null) ? total : 0;
                notificationManager.showBackupProgressNotification(s, t);
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
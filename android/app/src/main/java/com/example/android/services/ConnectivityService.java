package com.example.android.services;

import android.app.Notification;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import androidx.annotation.Nullable;

import com.example.android.data.datasource.SystemDataSource;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.domain.enums.ConnectionType;
import com.example.android.enums.Channel;
import com.example.android.enums.DeviceInfoChannels;
import com.example.android.enums.SessionChannels;
import com.example.android.network.handlers.ChannelHandlerRegistry;
import com.example.android.network.handlers.DeviceInfoChannelHandler;
import com.example.android.network.handlers.PCNameChannelHandler;
import com.example.android.network.handlers.DisconnectChannelHandler;
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
        registerChannelHandlers();

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
            sendDisconnectToPC();
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
}
package com.example.android.services;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

import com.example.android.R;
import com.example.android.data.datasource.SystemDataSource;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.domain.enums.ConnectionType;
import com.example.android.enums.DeviceInfoChannels;
import com.example.android.network.handlers.BatteryLevelChannelHandler;
import com.example.android.network.handlers.ChannelHandlerRegistry;
import com.example.android.network.handlers.PCNameChannelHandler;
import com.example.android.network.transport.TransportManager;
import com.example.android.network.transport.TransportStatus;
import com.example.android.network.transport.TauSyncTransportManager;
import com.example.android.repositories.DeviceRepository;

/**
 * ConnectivityService - Orchestrator for managing remote PC connections.
 *
 * Responsibilities:
 * ✓ Initialize and manage TransportManager
 * ✓ Register channel-specific handlers
 * ✓ Update Repository with connection status
 * ✓ Manage foreground notifications
 * ✓ Handle service lifecycle
 *
 * What it DOES NOT do (delegated):
 * ✗ Direct TauSync communication (→ TauSyncTransportManager)
 * ✗ Channel-specific logic (→ ChannelHandlers)
 * ✗ State management (→ DeviceRepository)
 *
 * This clean architecture makes it easy to:
 * - Add new transport types (Bluetooth, P2P, etc.)
 * - Add new channels (clipboard, file transfer, camera, etc.)
 * - Test individual components
 * - Scale without creating monolithic code
 */
public class ConnectivityService extends Service implements TransportManager.TransportListener {

    private static final String CHANNEL_ID = "ConnectivityServiceChannel";
    private static final String TAG = "TauSyncFlow";

    // Core components
    private TransportManager transportManager;
    private ChannelHandlerRegistry handlerRegistry;
    private SystemDataSource systemDataSource;
    private DeviceRepository deviceRepository;

    @Override
    public void onCreate() {
        super.onCreate();
        Log.d(TAG, "Service created");

        // Initialize dependencies
        systemDataSource = new SystemDataSource(this);

        // Initialize Repository (with fallback for Android 14+ race condition)
        try {
            deviceRepository = DeviceRepository.getInstance();
        } catch (IllegalStateException e) {
            Log.w(TAG, "Repository not initialized, initializing with fallback data");
            deviceRepository = DeviceRepository.getInstance(
                    systemDataSource.getDeviceId(),
                    systemDataSource.getDeviceModel()
            );
        }

        // Initialize transport manager (uses TauSync under the hood)
        transportManager = new TauSyncTransportManager();

        // Initialize channel handler registry
        handlerRegistry = new ChannelHandlerRegistry();
        registerChannelHandlers();

        createNotificationChannel();
        Log.d(TAG, "Service initialization complete");
    }

    /**
     * Registers all channel handlers.
     * This is where new handlers are wired in.
     * Future: clipboard, file transfer, camera streaming, etc.
     */
    private void registerChannelHandlers() {
        Log.d(TAG, "Registering channel handlers...");

        // Battery level handler
        handlerRegistry.registerHandler(
                DeviceInfoChannels.BATTERY_LEVEL.getValue(),
                new BatteryLevelChannelHandler(systemDataSource, transportManager)
        );

        // PC name handler
        handlerRegistry.registerHandler(
                DeviceInfoChannels.PC_NAME.getValue(),
                new PCNameChannelHandler(deviceRepository, transportManager)
        );

        // Future implementations:
        // handlerRegistry.registerHandler(
        //     "clipboard",
        //     new ClipboardChannelHandler(clipboard, transportManager)
        // );
        // handlerRegistry.registerHandler(
        //     "files",
        //     new FileTransferChannelHandler(fileManager, transportManager)
        // );
        // handlerRegistry.registerHandler(
        //     "camera",
        //     new CameraStreamChannelHandler(camera, transportManager)
        // );

        Log.d(TAG, "Registered " + handlerRegistry.getHandlerCount() + " handlers");
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.d(TAG, "onStartCommand: Service starting");

        String targetIp = (intent != null) ? intent.getStringExtra("TARGET_IP") : null;
        Log.d(TAG, "Target IP: " + targetIp);

        if (targetIp == null) {
            Log.e(TAG, "No TARGET_IP provided, stopping service");
            stopSelf();
            return START_NOT_STICKY;
        }

        // Create RemoteDeviceInfo from the IP
        // ConnectionType will be set dynamically by transport layer
        RemoteDeviceInfo remoteDevice = new RemoteDeviceInfo(
                "PC",           // Name (will be updated via channel handler)
                targetIp,
                ConnectionType.WIFI  // Default; can be changed dynamically
        );

        // Update repository status to CONNECTING
        deviceRepository.updateConnectionStatus(ConnectionStatus.CONNECTING);

        // Start initial notification
        showConnectingNotification(targetIp);

        // Request connection from transport manager
        // This will trigger the connection attempt with automatic reconnect
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
        cleanup();
        super.onDestroy();
    }

    private void cleanup() {
        if (handlerRegistry != null) {
            handlerRegistry.shutdownAll();
        }
        if (transportManager != null) {
            transportManager.shutdown();
        }
        deviceRepository.updateConnectionStatus(ConnectionStatus.DISCONNECTED);
    }

    // ============ TransportListener Implementation ============
    // These methods are called by the TransportManager when status changes

    @Override
    public void onStatusChanged(TransportStatus status) {
        Log.d(TAG, "Transport status changed: " + status);

        // Map TransportStatus to ConnectionStatus for the UI
        ConnectionStatus connectionStatus = mapTransportStatusToConnectionStatus(status);
        deviceRepository.updateConnectionStatus(connectionStatus);

        // Update notification
        updateNotificationForTransportStatus(status);
    }

    @Override
    public void onPeerRequestsAvailable(java.util.List<String> channels) {
        Log.d(TAG, "Peer requests available for channels: " + channels);

        // Send initial device info once on first connection
        if (deviceRepository.getCurrentConnectionStatus() == ConnectionStatus.CONNECTED &&
                transportManager.isConnected()) {

            // Check if we've already sent initial data
            boolean shouldSendInitialData = false;
            try {
                String name = transportManager.readFromChannel(DeviceInfoChannels.NAME.getValue());
                shouldSendInitialData = name == null || name.isEmpty();
            } catch (Exception e) {
                shouldSendInitialData = true;  // Assume we haven't sent yet on error
            }

            if (shouldSendInitialData) {
                sendInitialDeviceInfo();
            }
        }

        // Delegate to channel-specific handlers
        for (String channel : channels) {
            handlerRegistry.handlePeerRequest(channel);
        }
    }

    @Override
    public void onConnectionError(Exception error) {
        Log.e(TAG, "Connection error: " + error.getMessage(), error);
        deviceRepository.updateConnectionStatus(ConnectionStatus.FAILED);
        updateNotification("Connection failed");
    }

    @Override
    public void onReconnectAttempt(int attemptNumber, int maxRetries) {
        Log.i(TAG, "Reconnect attempt " + attemptNumber + "/" + maxRetries);
        deviceRepository.updateConnectionStatus(ConnectionStatus.RECONNECTING);
        updateNotification("Reconnecting... (attempt " + attemptNumber + "/" + maxRetries + ")");
    }

    // ============ Helper Methods ============

    /**
     * Maps TransportStatus to ConnectionStatus for the repository.
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
     * Updates notification based on transport status.
     */
    private void updateNotificationForTransportStatus(TransportStatus status) {
        switch (status) {
            case CONNECTED:
                updateNotification("Connected to PC");
                break;
            case CONNECTING:
                updateNotification("Connecting...");
                break;
            case RECONNECTING:
                updateNotification("Reconnecting...");
                break;
            case FAILED:
                updateNotification("Connection failed");
                break;
            case DISCONNECTING:
            case IDLE:
            default:
                updateNotification("Disconnected");
        }
    }

    /**
     * Sends initial device information to the remote PC.
     * Called once when connection is first established.
     */
    private void sendInitialDeviceInfo() {
        Log.d(TAG, "Sending initial device info");
        try {
            sendDeviceInfo(DeviceInfoChannels.NAME.getValue(), systemDataSource.getDeviceModel());
            sendDeviceInfo(DeviceInfoChannels.OS.getValue(), "Android " + Build.VERSION.RELEASE);
            sendDeviceInfo(DeviceInfoChannels.ID.getValue(), systemDataSource.getDeviceId());
            sendDeviceInfo(DeviceInfoChannels.IP.getValue(), systemDataSource.getLocalIp());
            sendDeviceInfo(DeviceInfoChannels.BATTERY_LEVEL.getValue(), String.valueOf(systemDataSource.getBattery()));
            sendDeviceInfo(DeviceInfoChannels.BATTERY_CHARGING.getValue(), String.valueOf(systemDataSource.isDeviceCharging()));
            sendDeviceInfo(DeviceInfoChannels.STORAGE_TOTAL.getValue(), String.valueOf(systemDataSource.getRawStorageStats().getTotal()));
            sendDeviceInfo(DeviceInfoChannels.STORAGE_USED.getValue(), String.valueOf(systemDataSource.getRawStorageStats().getUsed()));
        } catch (Exception e) {
            Log.e(TAG, "Error sending initial device info: " + e.getMessage(), e);
        }
    }

    private void sendDeviceInfo(String channel, String value) {
        try {
            Log.v(TAG, "Sending [" + channel + "]: " + value);
            transportManager.writeToChannel(channel, value);
        } catch (Exception e) {
            Log.e(TAG, "Error writing [" + channel + "]: " + e.getMessage());
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "Connectivity Service Channel",
                    NotificationManager.IMPORTANCE_LOW
            );
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    private void showConnectingNotification(String targetIp) {
        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle(getString(R.string.app_name))
                .setContentText("Connecting to " + targetIp + "...")
                .setSmallIcon(R.drawable.ic_sync)
                .setOngoing(true)
                .build();

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(1, notification, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(1, notification);
        }
    }

    private void updateNotification(String status) {
        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle(getString(R.string.app_name))
                .setContentText(status)
                .setSmallIcon(R.drawable.ic_sync)
                .setOngoing(true)
                .build();

        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.notify(1, notification);
        }
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}

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
 * Manages notification lifecycle and listens to repository changes directly.
 */
public class ConnectivityService extends Service implements TransportManager.TransportListener {

    private static final String TAG = "TauSyncFlow";

    // Core components
    private TransportManager transportManager;
    private ChannelHandlerRegistry handlerRegistry;
    private SystemDataSource systemDataSource;
    private DeviceRepository deviceRepository;
    private AppNotificationManager notificationManager;

    @Override
    public void onCreate() {
        super.onCreate();
        Log.d(TAG, "Service created");

        // 1. Initialize notification manager and START LISTENING
        // This ensures notification updates work even if the Activity is destroyed.
        notificationManager = new AppNotificationManager(this);
        notificationManager.startListeningToConnectionChanges();

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

        Log.d(TAG, "Service initialization complete");
    }

    private void registerChannelHandlers() {
        Log.d(TAG, "Registering channel handlers...");

        handlerRegistry.registerHandler(
                DeviceInfoChannels.BATTERY_LEVEL.getValue(),
                new BatteryLevelChannelHandler(systemDataSource, transportManager)
        );

        handlerRegistry.registerHandler(
                DeviceInfoChannels.PC_NAME.getValue(),
                new PCNameChannelHandler(deviceRepository, transportManager)
        );

        Log.d(TAG, "Registered " + handlerRegistry.getHandlerCount() + " handlers");
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.d(TAG, "onStartCommand: Service starting");

        // Immediate startForeground to satisfy system requirements
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

        // 2. STOP LISTENING to prevent memory leaks
        if (notificationManager != null) {
            notificationManager.stopListeningToConnectionChanges();
        }

        cleanup();
        super.onDestroy();
    }

    private void cleanup() {
        Log.d(TAG, "Cleanup started - stopping threads and shutting down network");

        if (handlerRegistry != null) {
            handlerRegistry.shutdownAll();
        }
        if (transportManager != null) {
            transportManager.shutdown();
        }
        if (deviceRepository != null) {
            // CRITICAL: Call disconnect() instead of just updateConnectionStatus.
            // This clears the RemotePC object from the state, ensuring the app 
            // starts on the Connect screen next time it's launched after a Swipe.
            deviceRepository.disconnect();
        }
    }

    // ============ TransportListener Implementation ============

    @Override
    public void onStatusChanged(TransportStatus status) {
        Log.d(TAG, "Transport status changed: " + status);

        ConnectionStatus connectionStatus = mapTransportStatusToConnectionStatus(status);
        deviceRepository.updateConnectionStatus(connectionStatus);

        if (status == TransportStatus.CONNECTED) {
            sendInitialDeviceInfo();
        }
    }

    @Override
    public void onPeerRequestsAvailable(java.util.List<String> channels) {
        Log.d(TAG, "Peer requests available for channels: " + channels);

        if (deviceRepository.getCurrentConnectionStatus() == ConnectionStatus.CONNECTED &&
                transportManager.isConnected()) {

            boolean shouldSendInitialData = false;
            try {
                String name = transportManager.readFromChannel(DeviceInfoChannels.NAME.getValue());
                shouldSendInitialData = name == null || name.isEmpty();
            } catch (Exception e) {
                shouldSendInitialData = true;
            }

            if (shouldSendInitialData) {
                sendInitialDeviceInfo();
            }
        }

        for (String channel : channels) {
            handlerRegistry.handlePeerRequest(channel);
        }
    }

    @Override
    public void onConnectionError(Exception error) {
        Log.e(TAG, "Connection error: " + error.getMessage(), error);
        deviceRepository.updateConnectionStatus(ConnectionStatus.FAILED);
    }

    @Override
    public void onReconnectAttempt(int attemptNumber, int maxRetries) {
        Log.i(TAG, "Reconnect attempt " + attemptNumber + "/" + maxRetries);
        deviceRepository.updateConnectionStatus(ConnectionStatus.RECONNECTING);
    }

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

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}

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
import com.example.android.domain.entities.DeviceConnectionState;
import com.example.android.domain.entities.DeviceStorageStats;
import com.example.android.domain.entities.LocalDeviceInfo;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionType;
import com.example.android.enums.DeviceInfoChannels;
import com.example.android.data.datasource.SystemDataSource;
import com.example.android.repositories.DeviceRepository;
import com.example.android.utils.NetworkHandler;
import com.example.tausync_lib.sdk.TauSync;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Foreground service responsible for maintaining the lifecycle of the TauSync connection.
 * It manages data streaming between the Android device and the desktop peer,
 * handles background polling for peer requests, and provides persistent status via notifications.
 */
public class ConnectivityService extends Service {
    private static final String CHANNEL_ID = "ConnectivityServiceChannel";
    private TauSync tauSync;
    private SystemDataSource systemDataSource;
    private DeviceConnectionState connectionState;
    private final ExecutorService backgroundExecutor = Executors.newCachedThreadPool();

    @Override
    public void onCreate() {
        super.onCreate();

        DeviceRepository deviceRepository = DeviceRepository.getInstance();

        this.connectionState = deviceRepository.getCurrentConnectionState();

        createNotificationChannel();
        systemDataSource = new SystemDataSource(this);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // 1. Extract the target IP address provided by the QR code scanner
        String targetIp = intent.getStringExtra("TARGET_IP");

        if (connectionState != null && connectionState.getRemotePC() != null) {
            connectionState.getRemotePC().setConnectionType(ConnectionType.WIFI);
//            deviceRepository.notifyStatusChanged(); // עדכון ה-UI שהתחלנו חיבור WIFI
        }

        // 2. Initialize foreground notification to prevent the system from killing the service
        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("SyncApp")
                .setContentText("Connecting to " + targetIp + "...")
                .setSmallIcon(R.drawable.ic_sync)
                .build();
        startForeground(1, notification);

        // 3. Initiate TCP connection on a background thread to avoid ANR
        if (targetIp != null) {
            backgroundExecutor.execute(() -> {
                try {
                    tauSync = new TauSync();
                    tauSync.connectTo(targetIp); // Handshake with PC client

                    // Update UI status upon successful transport establishment
                    updateNotification("Connected to PC at " + targetIp);

                    // 4. Begin the bidirectional data exchange protocol
                    startDataStreaming();

                } catch (Exception e) {
                    updateNotification("Connection failed: " + e.getMessage());
                    Log.e("ConnectivityService", "Failed to establish TauSync transport", e);
                }
            });
        }

        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        // Resource cleanup: dispose transport and shutdown background executors
        if (tauSync != null) tauSync.dispose();
        backgroundExecutor.shutdownNow();
    }

    /**
     * Required for Android O and above to display foreground notifications.
     */
    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel serviceChannel = new NotificationChannel(
                    CHANNEL_ID,
                    "Connectivity Service Channel",
                    NotificationManager.IMPORTANCE_LOW
            );
            NotificationManager manager = getSystemService(NotificationManager.class);
            manager.createNotificationChannel(serviceChannel);
        }
    }

    /**
     * Updates the existing foreground notification with the current connection status.
     * @param statusText Descriptive text to display in the notification body.
     */
    private void updateNotification(String statusText) {
        String appName = getString(R.string.app_name);

        Notification updatedNotification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle(appName + " - Connected")
                .setContentText(statusText)
                .setSmallIcon(R.drawable.ic_sync)
                .setOngoing(true)
                .build();

        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        manager.notify(1, updatedNotification);
    }

    /**
     * Manages the synchronization loop.
     * Sends initial device metadata and then polls for incoming requests from the peer.
     */
    private void startDataStreaming() {
        backgroundExecutor.execute(() -> {
            try {
                // Phase A: Push initial static device info required for the desktop handshake
                sendInitialStaticData();

                // Phase B: Enter polling loop to monitor 'Waiting Words' from the peer
                while (tauSync != null && !backgroundExecutor.isShutdown()) {
                    List<String> waitingWords = tauSync.getPeerWaitingWords();

                    if (!waitingWords.isEmpty()) {
                        handlePeerRequests(waitingWords);
                    }

                    // Throttling the loop to preserve battery and CPU cycles
                    Thread.sleep(2000);
                }
            } catch (Exception e) {
                Log.e("ConnectivityService", "Streaming loop interrupted", e);
            }
        });
    }

    /**
     * Populates the TauSync channels with hardware and OS metadata.
     * These channels are typically read by the desktop's 'get_device_info' method.
     */
    private void sendInitialStaticData() {
        NetworkHandler.writeToChannel(tauSync, DeviceInfoChannels.NAME.getValue(), systemDataSource.getDeviceModel());
        NetworkHandler.writeToChannel(tauSync, DeviceInfoChannels.OS.getValue(), "Android " + Build.VERSION.RELEASE);
        NetworkHandler.writeToChannel(tauSync, DeviceInfoChannels.ID.getValue(), systemDataSource.getDeviceId());
        NetworkHandler.writeToChannel(tauSync, DeviceInfoChannels.IP.getValue(), systemDataSource.getLocalIp());

        // Send initial telemetry data
        NetworkHandler.writeToChannel(tauSync, DeviceInfoChannels.BATTERY_LEVEL.getValue(),
                String.valueOf(systemDataSource.getBattery()));

        // send if charging
        boolean isCharging = systemDataSource.isDeviceCharging();
        NetworkHandler.writeToChannel(tauSync,
                DeviceInfoChannels.BATTERY_CHARGING.getValue(),
                String.valueOf(isCharging));

        // Transmit raw storage metrics for desktop processing
        DeviceStorageStats storage = systemDataSource.getRawStorageStats();
        NetworkHandler.writeToChannel(tauSync, DeviceInfoChannels.STORAGE_TOTAL.getValue(), String.valueOf(storage.getTotal()));
        NetworkHandler.writeToChannel(tauSync, DeviceInfoChannels.STORAGE_USED.getValue(), String.valueOf(storage.getUsed()));
    }

    /**
     * Reacts to specific requests flagged by the desktop peer via the Waiting Words list.
     * @param waiting List of words (channels) the peer is currently attempting to connect to.
     */
    private void handlePeerRequests(List<String> waiting) {
        // Handle PC Name retrieval if the peer is exposing its hostname
        if (waiting.contains(DeviceInfoChannels.PC_NAME.getValue())) {
            String pcName = NetworkHandler.readFromChannel(tauSync, DeviceInfoChannels.PC_NAME.getValue());
            if (!pcName.isEmpty()) {
                if (connectionState != null && connectionState.getRemotePC() != null) {
                    connectionState.getRemotePC().setPcName(pcName);
                }
                updateNotification("Connected to " + pcName);
            }
        }

        // Handle recurring telemetry updates (e.g., requested battery refresh)
        if (waiting.contains(DeviceInfoChannels.BATTERY_LEVEL.getValue())) {
            NetworkHandler.writeToChannel(tauSync, DeviceInfoChannels.BATTERY_LEVEL.getValue(),
                    String.valueOf(systemDataSource.getBattery()));
        }
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        // Binding not yet implemented; communication via StartCommand for now.
        return null;
    }
}
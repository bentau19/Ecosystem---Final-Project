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

public class ConnectivityService extends Service {
    private static final String CHANNEL_ID = "ConnectivityServiceChannel";
    private static final String TAG = "TauSyncFlow";
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
        String targetIp = intent.getStringExtra("TARGET_IP");
        Log.d(TAG, "onStartCommand: Starting service for IP: " + targetIp);

        if (connectionState != null && connectionState.getRemotePC() != null) {
            connectionState.getRemotePC().setConnectionType(ConnectionType.WIFI);
        }

        // נוטיפיקציה התחלתית
        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("SyncApp")
                .setContentText("Connecting to " + targetIp + "...")
                .setSmallIcon(R.drawable.ic_sync)
                .setOngoing(true) // מונע החלקה של הנוטיפיקציה
                .build();
        startForeground(1, notification);

        if (targetIp != null) {
            backgroundExecutor.execute(() -> {
                try {
                    Log.i(TAG, "Attempting TCP connection to: " + targetIp);
                    tauSync = new TauSync();
                    tauSync.connectTo(targetIp);

                    Log.i(TAG, "✔ TCP Connection established successfully!");
                    updateNotification("Connected to PC at " + targetIp);

                    startDataStreaming();

                } catch (Exception e) {
                    Log.e(TAG, "✘ Connection failed: " + e.getMessage());

                    // פתרון לכישלון: עצירת ה-Foreground והסרוויס
                    stopForeground(true);
                    stopSelf();
                }
            });
        }

        return START_STICKY;
    }

    /**
     * פתרון לניקוי הנוטיפיקציה כשהאפליקציה נסגרת מה-Recents
     */
    @Override
    public void onTaskRemoved(Intent rootIntent) {
        Log.d(TAG, "App removed from task list. Shutting down service...");
        cleanup();
        stopSelf();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        Log.d(TAG, "onDestroy: Service is being destroyed");
        cleanup();
        super.onDestroy();
    }

    private void cleanup() {
        if (tauSync != null) {
            tauSync.dispose();
            tauSync = null;
        }
        backgroundExecutor.shutdownNow();
    }

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

    private void updateNotification(String statusText) {
        Notification updatedNotification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle(getString(R.string.app_name) + " - Connected")
                .setContentText(statusText)
                .setSmallIcon(R.drawable.ic_sync)
                .setOngoing(true)
                .build();

        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        manager.notify(1, updatedNotification);
    }

    private void startDataStreaming() {
        backgroundExecutor.execute(() -> {
            try {
                Log.d(TAG, "Phase A: Pushing initial device metadata...");
                sendInitialStaticData();

                Log.d(TAG, "Phase B: Entering polling loop...");
                while (tauSync != null && !backgroundExecutor.isShutdown()) {
                    List<String> waitingWords = tauSync.getPeerWaitingWords();
                    if (!waitingWords.isEmpty()) {
                        handlePeerRequests(waitingWords);
                    }
                    Thread.sleep(2000);
                }
            } catch (InterruptedException e) {
                // when we close the app
                Log.i(TAG, "Streaming loop stopped gracefully due to interruption.");
            } catch (Exception e) {
                Log.e(TAG, "Streaming loop error: ", e);
            }
        });
    }

    private void sendInitialStaticData() {
        writeWithLog(DeviceInfoChannels.NAME.getValue(), systemDataSource.getDeviceModel());
        writeWithLog(DeviceInfoChannels.OS.getValue(), "Android " + Build.VERSION.RELEASE);
        writeWithLog(DeviceInfoChannels.ID.getValue(), systemDataSource.getDeviceId());
        writeWithLog(DeviceInfoChannels.IP.getValue(), systemDataSource.getLocalIp());
        writeWithLog(DeviceInfoChannels.BATTERY_LEVEL.getValue(), String.valueOf(systemDataSource.getBattery()));
        writeWithLog(DeviceInfoChannels.BATTERY_CHARGING.getValue(), String.valueOf(systemDataSource.isDeviceCharging()));

        DeviceStorageStats storage = systemDataSource.getRawStorageStats();
        writeWithLog(DeviceInfoChannels.STORAGE_TOTAL.getValue(), String.valueOf(storage.getTotal()));
        writeWithLog(DeviceInfoChannels.STORAGE_USED.getValue(), String.valueOf(storage.getUsed()));
    }

    private void writeWithLog(String channel, String value) {
        Log.v(TAG, "Writing to channel [" + channel + "]: " + value);
        NetworkHandler.writeToChannel(tauSync, channel, value);
    }

    private void handlePeerRequests(List<String> waiting) {
        if (waiting.contains(DeviceInfoChannels.PC_NAME.getValue())) {
            String pcName = NetworkHandler.readFromChannel(tauSync, DeviceInfoChannels.PC_NAME.getValue());
            if (!pcName.isEmpty()) {
                if (connectionState != null && connectionState.getRemotePC() != null) {
                    connectionState.getRemotePC().setPcName(pcName);
                }
                updateNotification("Connected to " + pcName);
            }
        }
        if (waiting.contains(DeviceInfoChannels.BATTERY_LEVEL.getValue())) {
            NetworkHandler.writeToChannel(tauSync, DeviceInfoChannels.BATTERY_LEVEL.getValue(),
                    String.valueOf(systemDataSource.getBattery()));
        }
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
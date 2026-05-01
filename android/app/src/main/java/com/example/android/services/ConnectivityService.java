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
import com.example.android.domain.entities.DeviceStorageStats;
import com.example.android.enums.DeviceInfoChannels;
import com.example.android.data.datasource.SystemDataSource;
import com.example.tausync_lib.sdk.TauSync;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ConnectivityService extends Service {
    private static final String CHANNEL_ID = "ConnectivityServiceChannel";
    private TauSync tauSync;
    private SystemDataSource systemDataSource;
    private final ExecutorService backgroundExecutor = Executors.newCachedThreadPool();

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        systemDataSource = new SystemDataSource(this);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // 1. חילוץ ה-IP שנשלח מה-QR
        String targetIp = intent.getStringExtra("TARGET_IP");

        // 2. הצגת נוטיפיקציה ראשונית
        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("SyncApp")
                .setContentText("Connecting to " + targetIp + "...")
                .setSmallIcon(R.drawable.ic_sync)
                .build();
        startForeground(1, notification);

        // 3. ביצוע החיבור ב-Thread נפרד
        if (targetIp != null) {
            backgroundExecutor.execute(() -> {
                try {
                    tauSync = new TauSync();
                    tauSync.connectTo(targetIp); // connect to PC

                    // update ui- notification that connection is successful
                    updateNotification("Connected to PC at " + targetIp);

                    // 4. כאן נתחיל להריץ את שליחת הנתונים
//                    startDataStreaming();

                } catch (Exception e) {
                    updateNotification("Connection failed: " + e.getMessage());
                }
            });
        }

        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        // סגירת החיבור וה-Threads כשמכבים את הסרוויס
        if (tauSync != null) tauSync.dispose();
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

    // פונקציית עזר בתוך ה-ConnectivityService
    private void updateNotification(String statusText) {
        String appName = getString(R.string.app_name);

        Notification updatedNotification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle(appName + " - Connected") // שינוי הכותרת
                .setContentText(statusText) // למשל: "Connected to MAY-PC"
                .setSmallIcon(R.drawable.ic_sync) // אפשר להחליף לאייקון של "וי"
                .setOngoing(true)
                .build();

        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        // שימוש באותו ID (שזה 1) גורם לאנדרואיד לעדכן את הנוטיפיקציה הקיימת במקום ליצור חדשה
        manager.notify(1, updatedNotification);
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null; // נשתמש בזה כשנרצה שהאקטיביטי תדבר עם הסרוויס
    }
}

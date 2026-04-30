package com.example.android.services;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import com.example.android.R;

public class ConnectivityService extends Service {
    private static final String CHANNEL_ID = "ConnectivityServiceChannel";

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String appName = getString(R.string.app_name);
        // יצירת הנוטיפיקציה שהמשתמש יראה למעלה
        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle(appName + " is running")
                .setContentText("Searching for PC connection...")
                .setSmallIcon(R.drawable.ic_sync) // וודאי שיש לך אייקון כזה
                .build();

        // הפעלת הסרוויס כ-Foreground (זה מה שמונע מהמערכת לסגור אותו)
        startForeground(1, notification);

        // כאן בהמשך יבוא הקוד של ה-Socket
        return START_STICKY;
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

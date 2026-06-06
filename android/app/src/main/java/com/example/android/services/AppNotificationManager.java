package com.example.android.services;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.os.Build;
import android.util.Log;

import androidx.core.app.NotificationCompat;
import androidx.lifecycle.Observer;

import com.example.android.R;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.repositories.DeviceRepository;

/**
 * AppNotificationManager - Responsible for managing connection status notifications.
 * It observes the connection status from the DeviceRepository and updates the system notification accordingly.
 */
public class AppNotificationManager {

    public static final String CHANNEL_ID = "ConnectivityServiceChannel";
    public static final int NOTIFICATION_ID = 1;
    private static final String TAG = "AppNotificationMgr";

    private final Context context;
    private final NotificationManager notificationManager;
    private Observer<ConnectionStatus> connectionStatusObserver;

    /**
     * Initializes the manager and creates the necessary notification channel.
     * @param context Application context.
     */
    public AppNotificationManager(Context context) {
        this.context = context.getApplicationContext();
        this.notificationManager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        createNotificationChannel();
    }

    /**
     * Starts listening to connection status changes from the Repository.
     * Updates the foreground notification text based on the current state.
     */
    public void startListeningToConnectionChanges() {
        Log.d(TAG, "Starting to listen for connection status changes");

        connectionStatusObserver = status -> {
            if (status == null) {
                Log.w(TAG, "Connection status is null");
                return;
            }

            Log.d(TAG, "Connection status changed: " + status);

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
                case DISCONNECTED:
                    dismissNotification();
                    break;
            }
        };

        try {
            DeviceRepository.getInstance()
                    .getConnectionStatus()
                    .observeForever(connectionStatusObserver);
        } catch (Exception e) {
            Log.e(TAG, "Failed to register observer: " + e.getMessage(), e);
        }
    }

    /**
     * Stops listening to connection status changes. 
     * Essential for preventing memory leaks when the service is destroyed.
     */
    public void stopListeningToConnectionChanges() {
        if (connectionStatusObserver != null) {
            try {
                DeviceRepository.getInstance()
                        .getConnectionStatus()
                        .removeObserver(connectionStatusObserver);
            } catch (Exception e) {
                Log.e(TAG, "Failed to unregister observer: " + e.getMessage(), e);
            }
        }
    }

    /**
     * Builds a notification object with the given content.
     * Public so ConnectivityService can use it for startForeground().
     * @param contentText The text to display in the notification.
     * @return The built Notification object.
     */
    public Notification buildNotification(String contentText) {
        return new NotificationCompat.Builder(context, CHANNEL_ID)
                .setContentTitle(context.getString(R.string.app_name))
                .setContentText(contentText)
                .setSmallIcon(R.drawable.ic_sync)
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build();
    }

    /**
     * Updates the active notification with new text.
     * @param contentText The new text to display.
     */
    private void updateNotification(String contentText) {
        if (notificationManager != null) {
            notificationManager.notify(NOTIFICATION_ID, buildNotification(contentText));
        }
    }

    /**
     * Removes the notification from the system tray.
     */
    private void dismissNotification() {
        if (notificationManager != null) {
            notificationManager.cancel(NOTIFICATION_ID);
        }
    }

    /**
     * Creates the notification channel required for Android O and above.
     */
    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "Connectivity Service Channel",
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Shows the status of PC connection");
            if (notificationManager != null) {
                notificationManager.createNotificationChannel(channel);
            }
        }
    }
}

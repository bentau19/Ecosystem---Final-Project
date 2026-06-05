package com.example.android.services;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
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
    public static final String FILE_TRANSFER_CHANNEL_ID = "FileTransferChannel";
    public static final int NOTIFICATION_ID = 1;
    public static final int FILE_TRANSFER_NOTIFICATION_ID = 2;
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
     * Shows a heads-up notification asking the user to Accept or Reject
     * an incoming file transfer from the PC.
     * Used when the app is in the background.
     *
     * @param fileName The name of the incoming file.
     * @param formattedSize Human-readable file size (e.g. "3.2 MB").
     */
    public void showFileTransferApprovalNotification(String fileName, String formattedSize) {
        // Accept PendingIntent
        Intent acceptIntent = new Intent(context, FileTransferActionReceiver.class);
        acceptIntent.setAction(FileTransferActionReceiver.ACTION_ACCEPT);
        PendingIntent acceptPending = PendingIntent.getBroadcast(
                context, 0, acceptIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        // Reject PendingIntent
        Intent rejectIntent = new Intent(context, FileTransferActionReceiver.class);
        rejectIntent.setAction(FileTransferActionReceiver.ACTION_REJECT);
        PendingIntent rejectPending = PendingIntent.getBroadcast(
                context, 1, rejectIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Notification notification = new NotificationCompat.Builder(context, FILE_TRANSFER_CHANNEL_ID)
                .setContentTitle("Incoming File from PC")
                .setContentText(fileName + " · " + formattedSize)
                .setSmallIcon(R.drawable.ic_sync)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .addAction(0, "Accept", acceptPending)
                .addAction(0, "Reject", rejectPending)
                .build();

        if (notificationManager != null) {
            notificationManager.notify(FILE_TRANSFER_NOTIFICATION_ID, notification);
        }
    }

    /**
     * Dismisses the file transfer approval notification.
     * Called after the user responds (either via dialog or notification).
     */
    public void dismissFileTransferNotification() {
        if (notificationManager != null) {
            notificationManager.cancel(FILE_TRANSFER_NOTIFICATION_ID);
        }
    }

    /**
     * Creates the notification channels required for Android O and above.
     */
    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            // Connectivity channel (low importance — persistent status bar)
            NotificationChannel connectivityChannel = new NotificationChannel(
                    CHANNEL_ID,
                    "Connectivity Service Channel",
                    NotificationManager.IMPORTANCE_LOW
            );
            connectivityChannel.setDescription("Shows the status of PC connection");

            // File transfer channel (high importance — heads-up notification)
            NotificationChannel fileTransferChannel = new NotificationChannel(
                    FILE_TRANSFER_CHANNEL_ID,
                    "File Transfer",
                    NotificationManager.IMPORTANCE_HIGH
            );
            fileTransferChannel.setDescription("Incoming file transfer requests from PC");

            if (notificationManager != null) {
                notificationManager.createNotificationChannel(connectivityChannel);
                notificationManager.createNotificationChannel(fileTransferChannel);
            }
        }
    }
}

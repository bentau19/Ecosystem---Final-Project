package com.example.android.utils;

import android.annotation.SuppressLint;
import android.content.Context;
import android.os.BatteryManager;
import android.os.Environment;
import android.os.StatFs;
import android.provider.Settings;

import java.io.File;

/**
 * Utility class for fetching hardware-related data from the Android system.
 * Provides methods for monitoring battery levels and storage capacity.
 */
public class DeviceUtils {

    @SuppressLint("HardwareIds")
    public static String getDeviceId(Context context) {
        return Settings.Secure.getString(
                context.getContentResolver(),
                Settings.Secure.ANDROID_ID
        );
    }

    public static String getDeviceModel() {
        return android.os.Build.MODEL;
    }

    /**
     * Retrieves the current battery charge level.
     * @param context Application or Activity context to access system services.
     * @return Current battery percentage (0-100).
     */
    public static int getBatteryPercentage(Context context) {
        BatteryManager bm = (BatteryManager) context.getSystemService(Context.BATTERY_SERVICE);
        if (bm != null) {
            return bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
        }
        return 0;
    }

    /**
     * Calculates the total internal storage capacity of the device.
     * @return Total storage size in bytes.
     */
    public static long getTotalStorage() {
        File path = Environment.getDataDirectory();
        StatFs stat = new StatFs(path.getPath());
        return stat.getTotalBytes();
    }

    /**
     * Calculates the currently available (free) internal storage space.
     * @return Available storage size in bytes.
     */
    public static long getAvailableStorage() {
        File path = Environment.getDataDirectory();
        StatFs stat = new StatFs(path.getPath());
        return stat.getAvailableBytes();
    }
}
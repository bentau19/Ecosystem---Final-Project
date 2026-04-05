package com.example.android.utils;

import android.content.Context;
import android.os.BatteryManager;
import android.os.Environment;
import android.os.StatFs;
import java.io.File;

public class DeviceUtils {

    /**
     * מחזיר את אחוז הסוללה הנוכחי
     */
    public static int getBatteryPercentage(Context context) {
        BatteryManager bm = (BatteryManager) context.getSystemService(Context.BATTERY_SERVICE);
        if (bm != null) {
            return bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
        }
        return 0;
    }

    /**
     * מחזיר את סך כל האחסון בבייטים
     */
    public static long getTotalStorage() {
        File path = Environment.getDataDirectory();
        StatFs stat = new StatFs(path.getPath());
        return stat.getTotalBytes();
    }

    /**
     * מחזיר את האחסון הפנוי בבייטים
     */
    public static long getAvailableStorage() {
        File path = Environment.getDataDirectory();
        StatFs stat = new StatFs(path.getPath());
        return stat.getAvailableBytes();
    }
}
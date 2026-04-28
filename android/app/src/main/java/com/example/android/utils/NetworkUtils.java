package com.example.android.utils;

import android.content.Context;
import android.net.wifi.WifiManager;
import android.text.format.Formatter;

public class NetworkUtils {
    public static String getLocalIpAddress(Context context) {
        WifiManager wifiManager = (WifiManager) context.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
        int ipInt = wifiManager.getConnectionInfo().getIpAddress();
        return (ipInt == 0) ? "Disconnected" : Formatter.formatIpAddress(ipInt);
    }
}

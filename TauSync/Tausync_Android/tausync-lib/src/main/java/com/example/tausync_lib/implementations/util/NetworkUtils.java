package com.example.tausync_lib.implementations.util;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Collections;
import java.util.Enumeration;
import java.util.Locale;

/**
 * Network helpers shared by the hybrid session setup. Kept tiny and dependency-free so the
 * Windows side can mirror it line-for-line.
 */
public final class NetworkUtils {

    private NetworkUtils() {}

    /**
     * Finds this device's local IPv4 address to advertise in WIFI_CONNECT_READY. Picks an
     * interface that is up, not loopback, not virtual, and not a Bluetooth/RNDIS tether adapter,
     * with a routable (non link-local) IPv4 address. Wireless interfaces are preferred over wired
     * so a device on Wi-Fi advertises the address the peer can actually reach.
     *
     * @return the chosen IPv4 address, or null when none is available (caller falls back)
     */
    public static String getLocalWifiIpAddress() {
        String wiredFallback = null;
        try {
            Enumeration<NetworkInterface> adapters = NetworkInterface.getNetworkInterfaces();
            if (adapters == null) return null;

            for (NetworkInterface adapter : Collections.list(adapters)) {
                if (!isUsableAdapter(adapter)) continue;

                String ipv4 = firstRoutableIpv4(adapter);
                if (ipv4 == null) continue;

                // Wireless adapters on Android are typically named "wlan0".
                if (adapter.getName().toLowerCase(Locale.ROOT).startsWith("wlan")) {
                    return ipv4;
                }
                if (wiredFallback == null) wiredFallback = ipv4;
            }
        } catch (Exception ignored) {
            // Fall through to the fallback / null.
        }
        return wiredFallback;
    }

    private static boolean isUsableAdapter(NetworkInterface adapter) throws Exception {
        if (!adapter.isUp() || adapter.isLoopback() || adapter.isVirtual()) return false;
        String name = adapter.getName().toLowerCase(Locale.ROOT);
        // Bluetooth PAN / USB tether adapters would advertise an address not reachable over the
        // fast Wi-Fi path.
        return !name.contains("bt") && !name.contains("bluetooth") && !name.contains("rndis");
    }

    private static String firstRoutableIpv4(NetworkInterface adapter) {
        Enumeration<InetAddress> addresses = adapter.getInetAddresses();
        for (InetAddress address : Collections.list(addresses)) {
            if (!(address instanceof Inet4Address)) continue;
            if (address.isLoopbackAddress() || address.isLinkLocalAddress()) continue;
            return address.getHostAddress();
        }
        return null;
    }
}

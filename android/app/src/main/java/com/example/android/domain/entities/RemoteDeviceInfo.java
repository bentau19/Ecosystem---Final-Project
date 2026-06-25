package com.example.android.domain.entities;

import com.example.android.domain.enums.ConnectionType;
import com.google.gson.annotations.SerializedName;

import java.util.HashMap;
import java.util.Map;

/**
 * Entity representing the remote computer connected to the Galaxy Bridge.
 * Stores hardware identification and real-time dynamic statistics received from the PC.
 */
public class RemoteDeviceInfo {
    private String pcName;
    @SerializedName("ip")
    private final String ipAddress;
    /** Bluetooth Classic MAC for the hybrid path; {@code null} for the Wi-Fi (IP) path. */
    private final String macAddress;
    private ConnectionType connectionType;

    // Stores flexible system stats (e.g., CPU temp, RAM usage) sent by the PC client
    private final Map<String, String> dynamicStats = new HashMap<>();

    /**
     * Wi-Fi constructor (IP-based). Delegates with no MAC — kept for the existing QR/Wi-Fi flow.
     */
    public RemoteDeviceInfo(String pcName, String ipAddress, ConnectionType type) {
        this(pcName, ipAddress, null, type);
    }

    /**
     * Full constructor. For the hybrid (Bluetooth) path pass the {@code macAddress} and a
     * {@code null} IP — the Wi-Fi IP is discovered over Bluetooth at connect time.
     */
    public RemoteDeviceInfo(String pcName, String ipAddress, String macAddress, ConnectionType type) {
        this.pcName = pcName;
        this.ipAddress = ipAddress;
        this.macAddress = macAddress;
        this.connectionType = type;
    }

    // Getters
    public String getPcName() { return pcName; }
    public String getPcIp() { return ipAddress; }
    /** The Bluetooth MAC for the hybrid path, or {@code null} for Wi-Fi. */
    public String getMacAddress() { return macAddress; }
    public ConnectionType getConnectionType() { return connectionType; }
    /**
     * Updates the PC name once it is retrieved via the network handshake.
     * @param pcName The hostname sent by the desktop client.
     */
    public void setPcName(String pcName) {
        this.pcName = pcName;
    }

    /**
     * Updates the connection type (e.g., once confirmed as WIFI/BLUETOOTH).
     * @param connectionType The active connection protocol.
     */
    public void setConnectionType(ConnectionType connectionType) {
        this.connectionType = connectionType;
    }

    /**
     * @return A map of dynamic system metrics provided by the remote host.
     */
    public Map<String, String> getDynamicStats() { return dynamicStats; }

    /**
     * Updates or inserts a specific system metric into the dynamic stats map.
     * @param key The identifier for the stat (e.g., "CPU_LOAD").
     * @param value The value associated with the metric.
     */
    public void updateStat(String key, String value) {
        this.dynamicStats.put(key, value);
    }
}
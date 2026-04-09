package com.example.android.data.models.entities;

import com.example.android.data.models.enums.ConnectionType;

import java.util.HashMap;
import java.util.Map;

/**
 * Entity representing the remote computer connected to the Galaxy Bridge.
 * Stores hardware identification and real-time dynamic statistics received from the PC.
 */
public class RemoteDeviceInfo {
    private final String pcName;
    private final String ipAddress;
    private final ConnectionType connectionType;

    // Stores flexible system stats (e.g., CPU temp, RAM usage) sent by the PC client
    private final Map<String, String> dynamicStats = new HashMap<>();

    public RemoteDeviceInfo(String pcName, String ipAddress, ConnectionType type) {
        this.pcName = pcName;
        this.ipAddress = ipAddress;
        this.connectionType = type;
    }

    // Getters
    public String getPcName() { return pcName; }
    public String getPcIp() { return ipAddress; }
    public ConnectionType getConnectionType() { return connectionType; }

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
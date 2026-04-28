package com.example.android.serializers;

import com.example.android.domain.entities.RemoteDeviceInfo;
import com.google.gson.Gson;

/**
 * Utility class for converting data objects to JSON strings and vice-versa.
 * Uses the Gson library to handle data exchange between the Android app and the PC client.
 */
public class DeviceSerializer {
    private final Gson gson = new Gson();

    /**
     * Converts a JSON string received from the PC into a RemoteDeviceInfo object.
     * @param json The raw JSON string from the network.
     * @return A RemoteDeviceInfo object, or null if parsing fails.
     */
    public RemoteDeviceInfo deserializeRemoteInfo(String json) {
        try {
            return gson.fromJson(json, RemoteDeviceInfo.class);
        } catch (Exception e) {
            e.printStackTrace();
            return null;
        }
    }

    /**
     * Converts a Java object into a JSON string for transmission back to the PC.
     * @param stats The data object (e.g., LocalDeviceInfo or stats map) to serialize.
     * @return A JSON formatted string.
     */
    public String serializeLocalInfo(Object stats) {
        return gson.toJson(stats);
    }
}
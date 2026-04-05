package com.example.android.data.serializers;

import com.example.android.data.models.entities.RemoteDeviceInfo;
import com.google.gson.Gson;

public class DeviceSerializer {
    private final Gson gson = new Gson();

    /**
     * הופך טקסט JSON לאובייקט של מחשב
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
     * הופך אובייקט לטקסט (בשביל לשלוח למחשב בחזרה)
     */
    public String serializeLocalStats(Object stats) {
        return gson.toJson(stats);
    }
}
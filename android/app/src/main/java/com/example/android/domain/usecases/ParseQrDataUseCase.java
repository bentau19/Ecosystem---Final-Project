package com.example.android.domain.usecases;

import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.serializers.DeviceSerializer;

/**
 * UseCase responsible for converting raw QR string data into a structured RemoteDeviceInfo object.
 * This is the first step in the connection pipeline after a successful scan.
 */
public class ParseQrDataUseCase {

    private final DeviceSerializer serializer;

    public ParseQrDataUseCase() {
        // מאתחלים את הסריאליזר שמשתמש ב-Gson כדי לפענח את ה-JSON
        this.serializer = new DeviceSerializer();
    }

    /**
     * Executes the parsing logic.
     * @param qr The raw JSON string scanned from the QR code.
     * @return A populated RemoteDeviceInfo object if valid; null otherwise.
     */
    public RemoteDeviceInfo execute(String qr) {
        // בדיקת בטיחות בסיסית
        if (qr == null || qr.isEmpty()) {
            return null;
        }

        // שימוש בסריאליזר כדי להפוך את ה-JSON מה-QR לאובייקט RemoteDeviceInfo
        // ה-Gson יחפש ב-JSON שדות כמו "pcName" ו-"ipAddress" ויכניס אותם לאובייקט
        RemoteDeviceInfo info = serializer.deserializeRemoteInfo(qr);

        // מחזירים את האובייקט המפוענח (יהיה null אם ה-JSON לא תקין)
        return info;
    }
}
package com.example.android.domain.usecases;

import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionType;

public class ParseQrDataUseCase {

    public RemoteDeviceInfo execute(String qr) {
        // כאן יהיה הפענוח האמיתי
        // DeviceSerializer serializer = new DeviceSerializer();
        // RemoteDeviceInfo remote = serializer.deserializeRemoteInfo(qrData);

        return new RemoteDeviceInfo("Ben-PC", "192.168.1.15", ConnectionType.WIFI);


    }
}


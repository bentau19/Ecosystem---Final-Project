package com.example.android.viewmodel;

import android.content.Context;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.data.models.entities.DeviceInfo;
import com.example.android.data.models.entities.LocalDeviceStats;
import com.example.android.data.models.entities.RemoteDeviceInfo;
import com.example.android.data.repositories.DeviceRepository;
import com.example.android.data.serializers.DeviceSerializer;
import com.example.android.utils.DeviceUtils;
import com.example.android.utils.NetworkUtils;

public class MainViewModel extends ViewModel {

    private final DeviceRepository repository = DeviceRepository.getInstance();

    public LiveData<DeviceInfo> getDeviceInfo() {
        return repository.getDeviceInfo();
    }

    /**
     * עדכון נתוני הטלפון (כולל ה-IP של הפלאפון עצמו)
     */
    public void refreshLocalDeviceStats(Context context, int battery, long totalStorage, long availableStorage) {
        // 1. קודם כל שולפים את ה-IP הנוכחי של הפלאפון
        String currentPhoneIp = NetworkUtils.getLocalIpAddress(context);

        // 2. בונים את האובייקט הלוקאלי עם ה-IP ששלפנו
        LocalDeviceStats stats = new LocalDeviceStats(
                android.os.Build.MODEL,
                currentPhoneIp, // ה-IP נכנס כאן כפרמטר השני
                battery,
                totalStorage,
                availableStorage
        );

        // 3. מעדכנים את הריפוזיטורי
        repository.updateLocalStats(stats);
    }

    /**
     * פונקציה מהירה לריענון ה-IP בלבד (שימושי כשמחליפים רשת WiFi)
     */
    public void refreshOnlyIp(Context context) {
        String ip = NetworkUtils.getLocalIpAddress(context);
        repository.updateLocalIpOnly(ip);
    }

    public void connectWithFullStats(Context context, String pcName, String pcIp, int battery, long total, long available) {
        // הכנת החלק הלוקאלי
        String currentPhoneIp = NetworkUtils.getLocalIpAddress(context);
        LocalDeviceStats local = new LocalDeviceStats(android.os.Build.MODEL, currentPhoneIp, battery, total, available);

        // הכנת החלק המרוחק
        RemoteDeviceInfo remote = new RemoteDeviceInfo(pcName, pcIp);

        // עדכון הכל בפעולה אחת ב-Repository
        repository.updateFullInfo(local, remote, true);
    }

    public boolean handleConnectionFromQR(Context context, String qrData) {
        // 1. ה-ViewModel משתמש ב-Serializer כדי להבין מה כתוב ב-QR
        DeviceSerializer serializer = new DeviceSerializer();
        RemoteDeviceInfo remote = serializer.deserializeRemoteInfo(qrData);

        // אם ה-QR לא תקין או ריק
        if (remote == null || remote.getPcIp() == null || remote.getPcIp().equals("0.0.0.0")) {
            return false; // מחזירים שקר כדי שה-Activity תדע שנכשלו
        }

        // 2. ה-ViewModel אוסף את נתוני המכשיר (הזזנו את זה לפה!)
        int battery = DeviceUtils.getBatteryPercentage(context);
        long total = DeviceUtils.getTotalStorage();
        long available = DeviceUtils.getAvailableStorage();

        String phoneIp = NetworkUtils.getLocalIpAddress(context);
        LocalDeviceStats local = new LocalDeviceStats(android.os.Build.MODEL, phoneIp, battery, total, available);

        // 3. מעדכנים את הריפוזיטורי
        repository.updateFullInfo(local, remote, true);
        return true; // הצלחנו!
    }

    /**
     * פקודת חיבור למחשב
     */
    public void connectToPc(String pcName, String pcIp) {
        RemoteDeviceInfo remote = new RemoteDeviceInfo(pcName, pcIp);
        repository.updateRemoteInfo(remote, true);
    }

    /**
     * פקודת ניתוק
     */
    public void disconnectFromPc() {
        repository.setConnectionStatus(false);
    }
}
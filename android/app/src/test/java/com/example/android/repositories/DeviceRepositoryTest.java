package com.example.android.repositories;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;
import com.example.android.data.repositories.DeviceRepository;
import com.example.android.domain.entities.DeviceConnectionState;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionType;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;

public class DeviceRepositoryTest {

    // הכלל הזה הכרחי כדי לבדוק LiveData ב-Unit Test
    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    private DeviceRepository repository;

    @Before
    public void setUp() {
        // זוכרת את ה-getInstance החכם שעשינו? אנחנו מאתחלים אותו כאן
        // בגלל שזה Singleton, חשוב לוודא שהוא נקי לפני כל טסט (נרחיב על זה בהמשך אם יצטרך)
        repository = DeviceRepository.getInstance("test_id", "Test Pixel 6");
    }

    @Test
    public void updateBattery_updatesLiveDataCorrectly() {
        // 1. Act: מעדכנים סוללה ל-85%
        repository.updateLocalBattery(85);

        // 2. Assert: מוודאים שה-LiveData מכיל את הערך החדש
        DeviceConnectionState state = repository.getConnectionState().getValue();

        // בודקים שהסוללה בתוך ה-LocalDeviceInfo עודכנה
        assertEquals(85, state.getLocalDevice().getBatteryLevel());
    }

    @Test
    public void updateLocalStats_updatesBatteryAndIp() {
        // השמות המדויקים מהקוד שלך:
        repository.updateLocalBattery(90);
        repository.updateLocalIp("10.0.0.5");

        DeviceConnectionState state = repository.getConnectionState().getValue();

        assertEquals(90, state.getLocalDevice().getBatteryLevel());
        assertEquals("10.0.0.5", state.getLocalDevice().getIpAddress());
    }

    @Test
    public void connect_updatesStateToConnected() {
        // אצלך הפונקציה היא connect ומקבלת שם, IP וסוג חיבור
        repository.connect("Ben-PC", "192.168.1.15", ConnectionType.WIFI);

        DeviceConnectionState state = repository.getConnectionState().getValue();

        // בודקים אם ה-PC עודכן נכון (זה מעיד על חיבור)
        assertNotNull(state.getRemotePC());
        assertEquals("Ben-PC", state.getRemotePC().getPcName());
    }

    @Test
    public void disconnect_clearsRemoteDevice() {
        // קודם נחבר
        repository.connect("Ben-PC", "192.168.1.15", ConnectionType.WIFI);

        // עכשיו ננתק (הפונקציה אצלך היא disconnect)
        repository.disconnect();

        DeviceConnectionState state = repository.getConnectionState().getValue();

        // בודקים שה-RemoteDevice חזר להיות null או אובייקט ריק (תלוי במימוש שלך)
        // אם המימוש שלך מאפס את ה-RemoteDevice בניתוק:
        assertTrue(state.getRemotePC() == null || state.getRemotePC().getPcName().isEmpty());
    }

    @Test
    public void updateLocalStats_whileDisconnected_stillUpdatesLocalDevice() {
        // 1. וודא שאנחנו מנותקים
        repository.disconnect();

        // 2. עדכון נתונים מקומיים
        repository.updateLocalBattery(42);

        // 3. בדיקה שהסוללה התעדכנה למרות שאין חיבור למחשב
        DeviceConnectionState state = repository.getConnectionState().getValue();
        assertEquals(42, state.getLocalDevice().getBatteryLevel());
    }

    @Test
    public void connect_toNewPc_overwritesOldPcInfo() {
        // 1. חיבור למחשב ראשון
        repository.connect("Old-PC", "1.1.1.1", ConnectionType.WIFI);

        // 2. חיבור למחשב שני בלי לנתק קודם
        repository.connect("New-PC", "2.2.2.2", ConnectionType.WIFI);

        DeviceConnectionState state = repository.getConnectionState().getValue();

        // 3. בדיקה שהמידע הוחלף
        assertEquals("New-PC", state.getRemotePC().getPcName());
        assertEquals("2.2.2.2", state.getRemotePC().getPcIp());
    }

    @Test
    public void updateIp_doesNotAffectOtherFields() {
        // הנתונים ההתחלתיים מה-getInstance ב-setUp הם "test_id" ו-"Test Pixel 6"
        repository.updateLocalIp("192.168.1.100");

        DeviceConnectionState state = repository.getConnectionState().getValue();

        // בדיקה שה-IP התעדכן אבל השאר נשאר
        assertEquals("192.168.1.100", state.getLocalDevice().getIpAddress());
        assertEquals("test_id", state.getLocalDevice().getDeviceId());
        assertEquals("Test Pixel 6", state.getLocalDevice().getModelName());
    }
}
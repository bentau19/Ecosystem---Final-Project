package com.example.android.serializers;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import com.example.android.domain.entities.LocalDeviceInfo;
import com.example.android.domain.entities.RemoteDeviceInfo;

import org.junit.Before;
import org.junit.Test;

public class DeviceSerializerTest {

    private DeviceSerializer serializer;

    @Before
    public void setUp() {
        // פונקציה שרצה לפני כל טסט ומכינה את הכלים
        serializer = new DeviceSerializer();
    }

    @Test
    public void serializeLocalDeviceInfo_returnsValidJson() {
        // 1. Arrange: מכינים אובייקט דמיוני
        LocalDeviceInfo info = new LocalDeviceInfo("id_123", "Pixel 6", "192.168.1.1");

        // 2. Act: מפעילים את ה-Serializer
        String jsonResult = serializer.serializeLocalInfo(info);

        // 3. Assert: בודקים שהתוצאה מכילה את מה שציפינו
        assertTrue(jsonResult.contains("id_123"));
        assertTrue(jsonResult.contains("Pixel 6"));
        assertTrue(jsonResult.contains("192.168.1.1"));
    }

    @Test
    public void deserializeRemoteInfo_withValidJson_returnsCorrectObject() {
        // הכנה - מחרוזת JSON שמתאימה לשדות של RemoteDeviceInfo
        // (ודאי שהשמות כאן תואמים לשמות המשתנים בתוך RemoteDeviceInfo)
        String rawJson = "{\"pcName\":\"MyWindowsPC\", \"ipAddress\":\"192.168.1.50\"}";

        // הפעלה - שימוש בשם הפונקציה האמיתי שלך
        RemoteDeviceInfo remote = serializer.deserializeRemoteInfo(rawJson);

        // בדיקה
        assertNotNull(remote);
        assertEquals("MyWindowsPC", remote.getPcName());
        assertEquals("192.168.1.50", remote.getPcIp());
    }

    @Test
    public void deserializeRemoteInfo_withMalformedJson_returnsNull() {
        // JSON שבור בכוונה (חסר גרשיים או סוגר)
        String brokenJson = "{\"pcName\":\"MyPC\", \"ip\":";

        RemoteDeviceInfo result = serializer.deserializeRemoteInfo(brokenJson);

        // אנחנו מצפים ל-null ולא לקריסה של האפליקציה
        assertNull("Should return null for broken JSON", result);
    }

    @Test
    public void deserializeRemoteInfo_withMissingFields_returnsObjectWithNulls() {
        // JSON תקין מבנית, אבל רק עם שם מחשב
        String incompleteJson = "{\"pcName\":\"OnlyName\"}";

        RemoteDeviceInfo result = serializer.deserializeRemoteInfo(incompleteJson);

        assertNotNull(result);
        assertEquals("OnlyName", result.getPcName());
        assertNull(result.getPcIp()); // מוודאים שה-IP פשוט נשאר null ולא הפיל את הכל
    }

    @Test
    public void serializeLocalStats_withEmptyObject_returnsJsonStructure() {
        // יצירת אובייקט עם ערכים ריקים
        LocalDeviceInfo emptyInfo = new LocalDeviceInfo("", "", "");

        String jsonResult = serializer.serializeLocalInfo(emptyInfo);

        assertNotNull(jsonResult);
        assertTrue(jsonResult.contains("{}") || jsonResult.contains("\"\""));
    }

}

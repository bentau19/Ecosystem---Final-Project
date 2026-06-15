package com.example.android.serializers;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import com.example.android.domain.entities.LocalDeviceInfo;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.serializers.DeviceSerializer;

import org.junit.Before;
import org.junit.Test;

/**
 * Unit tests for DeviceSerializer to ensure correct JSON transformation.
 */
public class DeviceSerializerTest {

    private DeviceSerializer serializer;

    @Before
    public void setUp() {
        // Initializes the serializer before each test execution
        serializer = new DeviceSerializer();
    }

    @Test
    public void serializeLocalDeviceInfo_returnsValidJson() {
        // 1. Arrange: Create a mock local device object
        LocalDeviceInfo info = new LocalDeviceInfo("id_123", "Pixel 6", "192.168.1.1");

        // 2. Act: Execute the serialization logic
        String jsonResult = serializer.serializeLocalInfo(info);

        // 3. Assert: Verify the resulting string contains the expected data
        assertTrue(jsonResult.contains("id_123"));
        assertTrue(jsonResult.contains("Pixel 6"));
        assertTrue(jsonResult.contains("192.168.1.1"));
    }

    @Test
    public void deserializeRemoteInfo_withValidJson_returnsCorrectObject() {
        // Arrange: Prepare a valid JSON string matching RemoteDeviceInfo fields
        String rawJson = "{\"pcName\":\"MyWindowsPC\", \"ip\":\"192.168.1.50\"}";

        // Act: Deserialize the raw JSON string back into an object
        RemoteDeviceInfo remote = serializer.deserializeRemoteInfo(rawJson);

        // Assert: Verify all properties were correctly mapped
        assertNotNull(remote);
        assertEquals("MyWindowsPC", remote.getPcName());
        assertEquals("192.168.1.50", remote.getPcIp());
    }

    @Test
    public void deserializeRemoteInfo_withMalformedJson_returnsNull() {
        // Arrange: Create an intentionally broken JSON string
        String brokenJson = "{\"pcName\":\"MyPC\", \"ip\":";

        // Act: Attempt to parse the malformed string
        RemoteDeviceInfo result = serializer.deserializeRemoteInfo(brokenJson);

        // Assert: Ensure the system returns null instead of crashing
        assertNull("Should return null for broken JSON", result);
    }

    @Test
    public void deserializeRemoteInfo_withMissingFields_returnsObjectWithNulls() {
        // Arrange: Valid JSON structure but with missing fields
        String incompleteJson = "{\"pcName\":\"OnlyName\"}";

        // Act: Parse the incomplete data
        RemoteDeviceInfo result = serializer.deserializeRemoteInfo(incompleteJson);

        // Assert: Verify the object is created but missing fields remain null
        assertNotNull(result);
        assertEquals("OnlyName", result.getPcName());
        assertNull(result.getPcIp());
    }

    @Test
    public void serializeLocalStats_withEmptyObject_returnsJsonStructure() {
        // Arrange: Create an object with empty string values
        LocalDeviceInfo emptyInfo = new LocalDeviceInfo("", "", "");

        // Act: Serialize the empty object
        String jsonResult = serializer.serializeLocalInfo(emptyInfo);

        // Assert: Ensure the result maintains a valid JSON format
        assertNotNull(jsonResult);
        assertTrue(jsonResult.contains("{}") || jsonResult.contains("\"\""));
    }
}
package com.example.android.repositories;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;

import com.example.android.data.repositories.DeviceRepository;
import com.example.android.domain.entities.DeviceConnectionState;
import com.example.android.domain.enums.ConnectionType;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;

import java.lang.reflect.Field;

/**
 * Unit tests for DeviceRepository to ensure data integrity and state management.
 */
public class DeviceRepositoryTest {

    // Forces LiveData to execute synchronously for testing purposes
    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    private DeviceRepository repository;

    @Before
    public void setUp() throws Exception {
        // Reset the Singleton instance using reflection to ensure test isolation
        Field instance = DeviceRepository.class.getDeclaredField("instance");
        instance.setAccessible(true);
        instance.set(null, null);

        // Initialize repository with test constants
        repository = DeviceRepository.getInstance("test_id", "Test Pixel 6");
    }

    @Test
    public void updateBattery_updatesLiveDataCorrectly() {
        // Arrange & Act
        repository.updateLocalBattery(85);

        // Assert: Verify that the LiveData observer would receive the new battery value
        DeviceConnectionState state = repository.getConnectionState().getValue();
        assertNotNull(state);
        assertEquals(85, state.getLocalDevice().getBatteryLevel());
    }

    @Test
    public void updateLocalStats_updatesBatteryAndIp() {
        // Act: Update multiple local device properties
        repository.updateLocalBattery(90);
        repository.updateLocalIp("10.0.0.5");

        // Assert: Ensure both values were correctly stored in the state
        DeviceConnectionState state = repository.getConnectionState().getValue();
        assertEquals(90, state.getLocalDevice().getBatteryLevel());
        assertEquals("10.0.0.5", state.getLocalDevice().getIpAddress());
    }

    @Test
    public void connect_updatesStateToConnected() {
        // Act: Simulate connecting to a PC
        repository.connect("Ben-PC", "192.168.1.15", ConnectionType.WIFI);

        // Assert: Verify the remote PC object is created and isConnected logic returns true
        DeviceConnectionState state = repository.getConnectionState().getValue();
        assertNotNull(state.getRemotePC());
        assertEquals("Ben-PC", state.getRemotePC().getPcName());
        assertTrue(state.isConnected());
    }

    @Test
    public void disconnect_clearsRemoteDevice() {
        // Arrange: Establish a connection first
        repository.connect("Ben-PC", "192.168.1.15", ConnectionType.WIFI);

        // Act: Disconnect the remote session
        repository.disconnect();

        // Assert: Ensure the remote PC reference is cleared (null)
        DeviceConnectionState state = repository.getConnectionState().getValue();
        assertNull(state.getRemotePC());
    }

    @Test
    public void updateLocalStats_whileDisconnected_stillUpdatesLocalDevice() {
        // Arrange: Start in a disconnected state
        repository.disconnect();

        // Act: Update local hardware info
        repository.updateLocalBattery(42);

        // Assert: Local stats should update regardless of remote connection status
        DeviceConnectionState state = repository.getConnectionState().getValue();
        assertEquals(42, state.getLocalDevice().getBatteryLevel());
    }

    @Test
    public void connect_toNewPc_overwritesOldPcInfo() {
        // Arrange: Connect to an initial PC
        repository.connect("Old-PC", "1.1.1.1", ConnectionType.WIFI);

        // Act: Connect to a different PC without explicit disconnection
        repository.connect("New-PC", "2.2.2.2", ConnectionType.WIFI);

        // Assert: Verify that the old connection info was replaced by the new one
        DeviceConnectionState state = repository.getConnectionState().getValue();
        assertEquals("New-PC", state.getRemotePC().getPcName());
        assertEquals("2.2.2.2", state.getRemotePC().getPcIp());
    }

    @Test
    public void updateIp_doesNotAffectOtherFields() {
        // Act: Change only the IP address
        repository.updateLocalIp("192.168.1.100");

        // Assert: Verify the IP changed while other identity fields remained intact
        DeviceConnectionState state = repository.getConnectionState().getValue();
        assertEquals("192.168.1.100", state.getLocalDevice().getIpAddress());
        assertEquals("test_id", state.getLocalDevice().getDeviceId());
        assertEquals("Test Pixel 6", state.getLocalDevice().getModelName());
    }
}
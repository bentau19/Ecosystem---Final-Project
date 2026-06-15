package com.example.android.viewmodel;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import androidx.arch.core.executor.testing.InstantTaskExecutorRule;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.repositories.DeviceRepository;
import com.example.android.domain.entities.DeviceConnectionState;
import com.example.android.domain.entities.LocalDeviceInfo;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionType;
import com.example.android.domain.usecases.ConnectToDeviceUseCase;
import com.example.android.domain.usecases.DisconnectDeviceUseCase;
import com.example.android.domain.usecases.ParseQrDataUseCase;
import com.example.android.domain.usecases.RefreshLocalStatsUseCase;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.mockito.Mock;
import org.mockito.junit.MockitoJUnitRunner;

/**
 * Unit tests for MainViewModel using Mockito to verify interaction with UseCases and Repository.
 */
@RunWith(MockitoJUnitRunner.class)
public class MainViewModelTest {

    // Rule to allow LiveData to work instantly in a JUnit environment
    @Rule
    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();

    @Mock
    private DeviceRepository mockRepository;

    @Mock
    private RefreshLocalStatsUseCase mockRefreshUseCase;

    @Mock
    private ConnectToDeviceUseCase mockConnectUseCase;

    @Mock
    private ParseQrDataUseCase mockParseQrUseCase;

    @Mock
    private DisconnectDeviceUseCase mockDisconnectUseCase;

    private MainViewModel viewModel;

    @Before
    public void setUp() {
        // Injecting mocked dependencies into the ViewModel
        viewModel = new MainViewModel(
                mockRepository,
                mockRefreshUseCase,
                mockConnectUseCase,
                mockParseQrUseCase,
                mockDisconnectUseCase
        );
    }

    @Test
    public void disconnect_callsDisconnectUseCase() {
        // Act: Trigger disconnect logic
        viewModel.disconnect();

        // Assert: DisconnectDeviceUseCase.execute() is called, not ConnectToDeviceUseCase
        verify(mockDisconnectUseCase).execute();
    }

    @Test
    public void getConnectionState_returnsLiveDataFromRepository() {
        // Arrange: Mock the repository state
        LocalDeviceInfo fakePhone = new LocalDeviceInfo("id", "Model", "1.1.1.1");
        DeviceConnectionState state = new DeviceConnectionState(fakePhone);
        state.setRemotePC(new RemoteDeviceInfo("Ben-PC", "192.168.1.15", ConnectionType.WIFI));

        MutableLiveData<DeviceConnectionState> fakeLiveData = new MutableLiveData<>();
        fakeLiveData.setValue(state);

        when(mockRepository.getConnectionState()).thenReturn(fakeLiveData);

        // Act: Retrieve LiveData from ViewModel
        LiveData<DeviceConnectionState> result = viewModel.getConnectionState();

        // Assert: Ensure data integrity across the flow
        assertEquals(state, result.getValue());
        assertTrue(result.getValue().isConnected());
        assertEquals("Ben-PC", result.getValue().getRemotePC().getPcName());
    }

    @Test
    public void refresh_callsRefreshUseCase() {
        // Act: Request data refresh
        viewModel.refresh();

        // Assert: Verify the execution of the refresh UseCase
        verify(mockRefreshUseCase).execute();
    }

    @Test
    public void handleQr_validData_callsConnectUseCase() {
        // Arrange: Setup successful QR parsing
        RemoteDeviceInfo fakeInfo =
                new RemoteDeviceInfo("Ben-PC", "192.168.1.15", ConnectionType.WIFI);

        when(mockParseQrUseCase.execute("qr_data")).thenReturn(fakeInfo);

        // Act: Process the QR data
        boolean result = viewModel.handleQr("qr_data");

        // Assert: Verify connection is initiated with correct parameters
        assertTrue(result);
        verify(mockConnectUseCase).execute(fakeInfo);
    }

    @Test
    public void handleQr_invalidData_returnsFalse() {
        // Arrange: Simulate a parsing failure
        when(mockParseQrUseCase.execute("bad_qr")).thenReturn(null);

        // Act: Process invalid QR
        boolean result = viewModel.handleQr("bad_qr");

        // Assert: Ensure failure is reported and no connection is attempted
        assertEquals(false, result);
    }
}
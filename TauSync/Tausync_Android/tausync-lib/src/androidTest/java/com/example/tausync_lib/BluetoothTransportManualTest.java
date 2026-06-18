package com.example.tausync_lib;

import static org.junit.Assert.assertTrue;

import android.Manifest;
import android.content.Context;

import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.rule.GrantPermissionRule;

import com.example.tausync_lib.core.CoreConfig;
import com.example.tausync_lib.implementations.protocol.ProtocolHandler;
import com.example.tausync_lib.implementations.transport.BluetoothTransport;
import com.example.tausync_lib.interfaces.IProtocolHandler;

import org.junit.Rule;
import org.junit.Test;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Manual hardware test for Phase 1 (see Bluetooth_Transport_Plan.md "Test after Phase 1").
 * Must run on a real device (Bluetooth Classic does not exist in the emulator), already
 * paired with the Windows PC via system Bluetooth settings, with the Windows counterpart
 * (BluetoothTransport.ManualTest) already running and advertising.
 *
 * <p>{@link GrantPermissionRule} grants BLUETOOTH_CONNECT/SCAN via the instrumentation's
 * UiAutomation before the test runs, so no manual {@code adb shell pm grant} step is
 * needed (and it works regardless of which user profile the test APK installs under).
 *
 * <p>Run with: {@code gradlew -p android :tausync-lib:connectedDebugAndroidTest}
 */
public class BluetoothTransportManualTest {

    // Replace with the paired Windows PC's Bluetooth MAC address.
    private static final String WINDOWS_MAC_ADDRESS = "04:E8:B9:C5:8A:8B";

    @Rule
    public GrantPermissionRule permissionRule = GrantPermissionRule.grant(
            Manifest.permission.BLUETOOTH_CONNECT,
            Manifest.permission.BLUETOOTH_SCAN);

    @Test
    public void connectsToWindowsAndExchangesData() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        BluetoothTransport transport = new BluetoothTransport(context);
        IProtocolHandler protocolHandler = new ProtocolHandler();
        CountDownLatch received = new CountDownLatch(1);

        transport.setOnDataReceivedListener(frame -> {
            IProtocolHandler.ParseResult result = protocolHandler.parseFrame(frame);
            String text = new String(result.getPayload(), StandardCharsets.UTF_8);
            System.out.println("[RECV] " + text);
            received.countDown();
        });

        transport.connect(WINDOWS_MAC_ADDRESS).get(CoreConfig.BT_CONNECT_TIMEOUT_MS, TimeUnit.MILLISECONDS);
        assertTrue("transport should report connected", transport.isConnected());

        byte[] frame = protocolHandler.buildFrame(
                CoreConfig.CONTROL_CHANNEL_ID,
                "hello from android".getBytes(StandardCharsets.UTF_8),
                CoreConfig.FLAG_CONTROL);
        transport.sendRaw(frame).get(5, TimeUnit.SECONDS);

        assertTrue("did not receive Windows's reply in time", received.await(15, TimeUnit.SECONDS));

        transport.disconnect();
    }
}

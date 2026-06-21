package com.example.tausync_lib.implementations.discovery;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.bluetooth.BluetoothDevice;
import android.companion.AssociationRequest;
import android.companion.BluetoothLeDeviceFilter;
import android.companion.CompanionDeviceManager;
import android.content.Context;
import android.content.IntentSender;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.ParcelUuid;

import androidx.annotation.Nullable;
import androidx.annotation.RequiresApi;

import com.example.tausync_lib.core.CoreConfig;

import java.util.regex.Pattern;

/**
 * Handles first-time Bluetooth pairing via BLE advertisement discovery.
 *
 * <p>The Windows PC advertises a BLE GATT service beacon carrying
 * {@link CoreConfig#BLE_SERVICE_UUID}. This class filters the scan to that UUID using
 * {@link CompanionDeviceManager}, which shows the OS-native pairing chooser rather than a custom
 * scan UI — so the user only ever sees the one TauSync PC, not every nearby BT device.
 *
 * <p>After successful pairing the device's Classic Bluetooth MAC address is saved to
 * SharedPreferences under {@link #PREFS_KEY_DEVICE_ADDRESS}. Subsequent launches read the saved
 * address directly via {@link #getSavedAddress(Context)} and skip BLE discovery entirely.
 * If the bond is later lost, {@link android.bluetooth.BluetoothTransport} catches
 * {@link com.example.tausync_lib.implementations.transport.BluetoothTransport.BondLostException}
 * and the caller triggers {@link #startDiscovery(Activity, PairingCallback)} again.
 *
 * <p>Requires API 26+ ({@link CompanionDeviceManager} minimum). Gate calls behind a version check
 * when {@code minSdk < 26} and fall back to manual MAC entry.
 */
@RequiresApi(api = Build.VERSION_CODES.O)
public class BleDiscovery {

    public static final int REQUEST_CODE_PAIRING = 1001;

    private static final String PREFS_NAME = "tausync_prefs";
    private static final String PREFS_KEY_DEVICE_ADDRESS = "tausync_bt_device_address";

    /**
     * Callback delivered on the main thread after the OS pairing chooser completes.
     */
    public interface PairingCallback {
        /** Called when the user selected and bonded a device. */
        void onDevicePaired(BluetoothDevice device);
        /** Called when discovery was cancelled or failed. */
        void onPairingFailed(String reason);
    }

    /**
     * Starts BLE scanning and shows the OS-native device chooser filtered to devices that
     * advertise {@link CoreConfig#BLE_SERVICE_UUID}. The chooser result must be forwarded to
     * {@link #onActivityResult(int, int, android.content.Intent, PairingCallback)} from the
     * activity's {@code onActivityResult}.
     *
     * @param activity activity used to launch the chooser intent
     * @param callback delivered when pairing succeeds or fails
     */
    @SuppressLint("MissingPermission")
    public void startDiscovery(Activity activity, PairingCallback callback) {
        android.bluetooth.le.ScanFilter scanFilter = new android.bluetooth.le.ScanFilter.Builder()
                .setServiceUuid(ParcelUuid.fromString(CoreConfig.BLE_SERVICE_UUID))
                .build();

        BluetoothLeDeviceFilter leFilter = new BluetoothLeDeviceFilter.Builder()
                .setScanFilter(scanFilter)
                .build();

        AssociationRequest request = new AssociationRequest.Builder()
                .addDeviceFilter(leFilter)
                .setSingleDevice(false)
                .build();

        CompanionDeviceManager cdm =
                (CompanionDeviceManager) activity.getSystemService(Context.COMPANION_DEVICE_SERVICE);
        if (cdm == null) {
            callback.onPairingFailed("CompanionDeviceManager not available");
            return;
        }

        cdm.associate(request, new CompanionDeviceManager.Callback() {
            @Override
            public void onDeviceFound(IntentSender chooserLauncher) {
                try {
                    // Launches the OS-managed picker that shows only TauSync-advertising PCs.
                    activity.startIntentSenderForResult(
                            chooserLauncher, REQUEST_CODE_PAIRING, null, 0, 0, 0);
                } catch (IntentSender.SendIntentException e) {
                    callback.onPairingFailed("Could not launch pairing chooser: " + e.getMessage());
                }
            }

            @Override
            public void onFailure(@Nullable CharSequence error) {
                callback.onPairingFailed(error != null ? error.toString() : "Discovery failed");
            }
        }, null);
    }

    /**
     * Must be called from the hosting Activity's {@code onActivityResult} to complete the
     * pairing flow. Delivers the paired device to {@code callback} on success.
     */
    public void onActivityResult(int requestCode, int resultCode,
                                  @Nullable android.content.Intent data,
                                  PairingCallback callback) {
        if (requestCode != REQUEST_CODE_PAIRING) return;
        if (resultCode != Activity.RESULT_OK || data == null) {
            callback.onPairingFailed("User cancelled pairing");
            return;
        }
        BluetoothDevice device = data.getParcelableExtra(CompanionDeviceManager.EXTRA_DEVICE);
        if (device != null) {
            callback.onDevicePaired(device);
        } else {
            callback.onPairingFailed("No device in pairing result");
        }
    }

    // ── SharedPreferences helpers ────────────────────────────────────────

    /**
     * Saves the paired device's Classic Bluetooth MAC address so future launches can skip
     * BLE discovery. Call this immediately after {@link PairingCallback#onDevicePaired}.
     */
    public static void savePairedAddress(Context context, String address) {
        prefs(context).edit().putString(PREFS_KEY_DEVICE_ADDRESS, address).apply();
    }

    /**
     * Returns the saved Bluetooth MAC address, or {@code null} if none was saved yet (i.e.,
     * this is a first run or the saved address was cleared).
     */
    @Nullable
    public static String getSavedAddress(Context context) {
        return prefs(context).getString(PREFS_KEY_DEVICE_ADDRESS, null);
    }

    /**
     * Removes the saved address. Use when the bond is lost and the user needs to re-pair from
     * scratch, or when resetting the device association.
     */
    public static void clearSavedAddress(Context context) {
        prefs(context).edit().remove(PREFS_KEY_DEVICE_ADDRESS).apply();
    }

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext()
                .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }
}

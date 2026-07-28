package com.example.tausync_lib.implementations.discovery;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanRecord;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;

import androidx.annotation.Nullable;

import com.example.tausync_lib.core.CoreConfig;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Collections;

/**
 * First-time Bluetooth pairing via a direct BLE scan controlled by the app.
 *
 * <p>The Windows PC advertises a connectionless BLE beacon whose manufacturer data carries the
 * {@code "TAUS"} magic, the PC's Bluetooth <b>Classic</b> MAC, and the PC name (see
 * {@code BleAdvertiser}). This class scans for that beacon with {@link BluetoothLeScanner}, and on
 * the first match reports the PC name + Classic {@link BluetoothDevice} to the caller via
 * {@link DiscoveryCallback} — the app then shows its own confirm dialog. If the user accepts, call
 * {@link #bond(Context, BluetoothDevice, PairingCallback)} to pair over Classic and save the MAC.
 *
 * <p>Unlike {@code CompanionDeviceManager}, this uses no OS chooser — the app owns the UI. Requires
 * {@code BLUETOOTH_SCAN} (scan) and {@code BLUETOOTH_CONNECT} (bond) at runtime on API 31+.
 */
public class BleDiscovery {

    private static final String PREFS_NAME = "tausync_prefs";
    private static final String PREFS_KEY_DEVICE_ADDRESS = "tausync_bt_device_address";

    /** Max time to scan before giving up and reporting failure. */
    private static final long SCAN_TIMEOUT_MS = 15_000;

    /** Reports the outcome of a BLE scan. Delivered off the main thread. */
    public interface DiscoveryCallback {
        /** A TauSync PC beacon was found. {@code classicDevice} is its Bluetooth Classic device. */
        void onPcFound(String pcName, BluetoothDevice classicDevice);
        /** No PC was found within the timeout, or the scan could not start. */
        void onDiscoveryFailed(String reason);
    }

    /** Reports the outcome of bonding the chosen PC. Delivered on the main thread. */
    public interface PairingCallback {
        /** The device is bonded and its address saved. */
        void onDevicePaired(BluetoothDevice device);
        /** Bonding failed or was rejected. */
        void onPairingFailed(String reason);
    }

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private BluetoothLeScanner scanner;
    private ScanCallback scanCallback;
    private volatile boolean scanHandled;

    // ── Discovery (direct BLE scan) ──────────────────────────────────────

    /**
     * Scans for the TauSync PC beacon. On the first match, stops scanning and delivers the PC name +
     * Classic device to {@code callback.onPcFound}; on timeout/error delivers {@code onDiscoveryFailed}.
     * Either callback fires exactly once.
     */
    @SuppressLint("MissingPermission")
    public void startScan(Context context, DiscoveryCallback callback) {
        Context appContext = context.getApplicationContext();
        BluetoothAdapter adapter = adapter(appContext);
        if (adapter == null || !adapter.isEnabled()) {
            callback.onDiscoveryFailed("Bluetooth is off or unavailable");
            return;
        }
        scanner = adapter.getBluetoothLeScanner();
        if (scanner == null) {
            callback.onDiscoveryFailed("BLE scanning is not available");
            return;
        }

        // Match the "TAUS" manufacturer-data magic only (mask covers just the 4 magic bytes), so the
        // trailing MAC + name bytes do not affect the match.
        byte[] magic = CoreConfig.BLE_BEACON_PAYLOAD;
        byte[] mask = new byte[magic.length];
        Arrays.fill(mask, (byte) 0xFF);
        ScanFilter filter = new ScanFilter.Builder()
                .setManufacturerData(CoreConfig.BLE_BEACON_COMPANY_ID, magic, mask)
                .build();
        ScanSettings settings = new ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
                .build();

        scanHandled = false;
        scanCallback = new ScanCallback() {
            @Override
            public void onScanResult(int callbackType, ScanResult result) {
                onBeacon(appContext, result, callback);
            }

            @Override
            public void onScanFailed(int errorCode) {
                if (!markHandled()) return;
                stopScan();
                callback.onDiscoveryFailed("BLE scan failed (code " + errorCode + ")");
            }
        };

        scanner.startScan(Collections.singletonList(filter), settings, scanCallback);

        mainHandler.postDelayed(() -> {
            if (!markHandled()) return;
            stopScan();
            callback.onDiscoveryFailed("No TauSync PC found nearby");
        }, SCAN_TIMEOUT_MS);
    }

    @SuppressLint("MissingPermission")
    private void onBeacon(Context context, ScanResult result, DiscoveryCallback callback) {
        if (scanHandled) return;

        ScanRecord record = result.getScanRecord();
        if (record == null) return;
        byte[] payload = record.getManufacturerSpecificData(CoreConfig.BLE_BEACON_COMPANY_ID);
        int macOffset = CoreConfig.BLE_BEACON_PAYLOAD.length;
        if (payload == null || payload.length < macOffset + 6) return;

        String mac = parseMac(payload, macOffset);
        if (mac == null) return; // all-zero MAC — PC could not read its own address
        BluetoothAdapter adapter = adapter(context);
        if (adapter == null) return;
        BluetoothDevice classic;
        try {
            classic = adapter.getRemoteDevice(mac);
        } catch (IllegalArgumentException e) {
            return;
        }

        String name = parseName(payload, macOffset + 6);
        if (name.isEmpty()) {
            String advertised = record.getDeviceName();
            name = advertised != null ? advertised : mac;
        }

        if (!markHandled()) return;
        stopScan();
        callback.onPcFound(name, classic);
    }

    /** Reads the 6 MAC bytes (most-significant first); null if all zero. */
    @Nullable
    private static String parseMac(byte[] payload, int offset) {
        boolean allZero = true;
        StringBuilder mac = new StringBuilder(17);
        for (int i = 0; i < 6; i++) {
            int b = payload[offset + i] & 0xFF;
            if (b != 0) allZero = false;
            if (i > 0) mac.append(':');
            mac.append(String.format("%02X", b));
        }
        return allZero ? null : mac.toString();
    }

    /** Reads the PC name that follows the MAC, or an empty string if absent. */
    private static String parseName(byte[] payload, int offset) {
        if (payload.length <= offset) return "";
        return new String(payload, offset, payload.length - offset, StandardCharsets.UTF_8).trim();
    }

    /** Stops any in-progress scan. Safe to call when not scanning. */
    @SuppressLint("MissingPermission")
    public void stopScan() {
        mainHandler.removeCallbacksAndMessages(null);
        BluetoothLeScanner activeScanner = scanner;
        ScanCallback activeCallback = scanCallback;
        if (activeScanner != null && activeCallback != null) {
            try {
                activeScanner.stopScan(activeCallback);
            } catch (Exception ignored) {
            }
        }
        scanCallback = null;
    }

    /** Returns true exactly once — guards against delivering the scan outcome more than once. */
    private synchronized boolean markHandled() {
        if (scanHandled) return false;
        scanHandled = true;
        return true;
    }

    // ── Bonding ──────────────────────────────────────────────────────────

    /**
     * Bonds the device if needed and reports the outcome. CompanionDeviceManager is not used; this
     * bonds the Classic device discovered in the beacon. The bond state arrives asynchronously via
     * a system broadcast, so success/failure is reported from the receiver.
     *
     * <p>Bonding deliberately does <b>not</b> remember the device. An OS bond only means the two
     * radios can talk — the PC has not yet accepted the connection, and it may well decline it. A
     * device remembered here would be redialled on every launch even after being turned away, with
     * no way back to discovery short of clearing app data. Call
     * {@link #savePairedAddress(Context, String)} once the session is actually established.
     */
    @SuppressLint("MissingPermission")
    public void bond(Context context, BluetoothDevice device, PairingCallback callback) {
        Context appContext = context.getApplicationContext();

        if (device.getBondState() == BluetoothDevice.BOND_BONDED) {
            callback.onDevicePaired(device);
            return;
        }

        BroadcastReceiver bondReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context ctx, Intent intent) {
                if (!BluetoothDevice.ACTION_BOND_STATE_CHANGED.equals(intent.getAction())) return;
                BluetoothDevice changed = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
                if (changed == null || !changed.getAddress().equals(device.getAddress())) return;

                int newState = intent.getIntExtra(
                        BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.ERROR);
                if (newState == BluetoothDevice.BOND_BONDED) {
                    appContext.unregisterReceiver(this);
                    callback.onDevicePaired(changed);
                } else if (newState == BluetoothDevice.BOND_NONE) {
                    // BOND_NONE after a bonding attempt means pairing failed or was rejected.
                    appContext.unregisterReceiver(this);
                    callback.onPairingFailed("Bonding failed for " + device.getAddress());
                }
                // BOND_BONDING is the in-progress transition — keep waiting.
            }
        };
        // ACTION_BOND_STATE_CHANGED is a protected system broadcast, so the 2-arg registerReceiver
        // is allowed even on API 34+ (no RECEIVER_EXPORTED/NOT_EXPORTED flag required).
        appContext.registerReceiver(
                bondReceiver, new IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED));

        if (!device.createBond()) {
            appContext.unregisterReceiver(bondReceiver);
            callback.onPairingFailed("Could not start bonding for " + device.getAddress());
        }
    }

    // ── SharedPreferences helpers ────────────────────────────────────────

    /**
     * Saves the paired device's Classic Bluetooth MAC address so future launches can skip
     * discovery. Call this only once a session with that device has actually been established —
     * see {@link #bond} for why a completed bond is not enough.
     */
    public static void savePairedAddress(Context context, String address) {
        prefs(context).edit().putString(PREFS_KEY_DEVICE_ADDRESS, address).apply();
    }

    /**
     * Returns the saved Bluetooth MAC address, or {@code null} if none was saved yet (first run or
     * the saved address was cleared).
     */
    @Nullable
    public static String getSavedAddress(Context context) {
        return prefs(context).getString(PREFS_KEY_DEVICE_ADDRESS, null);
    }

    /** Removes the saved address. Use when the bond is lost and the user needs to re-pair. */
    public static void clearSavedAddress(Context context) {
        prefs(context).edit().remove(PREFS_KEY_DEVICE_ADDRESS).apply();
    }

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext()
                .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    private static BluetoothAdapter adapter(Context context) {
        BluetoothManager manager =
                (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
        return manager != null ? manager.getAdapter() : null;
    }
}

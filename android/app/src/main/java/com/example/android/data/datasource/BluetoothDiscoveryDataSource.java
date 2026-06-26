package com.example.android.data.datasource;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.content.Context;

import androidx.annotation.Nullable;

import com.example.android.domain.entities.DiscoveredPc;
import com.example.android.domain.usecases.PairWithPcUseCase.DiscoveryListener;
import com.example.android.domain.usecases.PairWithPcUseCase.PairingListener;
import com.example.tausync_lib.implementations.discovery.BleDiscovery;

/**
 * Data-layer wrapper around the TauSync {@link BleDiscovery} library.
 *
 * <p>This is the only place in the app that touches Android Bluetooth framework types. It maps the
 * found {@link BluetoothDevice} to a framework-free {@link DiscoveredPc} (name + MAC string) so the
 * domain and UI stay clean. Bonding takes a MAC string (not a {@code BluetoothDevice}): the address
 * travels down from the ViewModel and is resolved back to a device here via
 * {@link BluetoothAdapter#getRemoteDevice(String)}. The callback contracts
 * ({@link DiscoveryListener}/{@link PairingListener}) are owned by the domain layer.
 */
public class BluetoothDiscoveryDataSource {

    private final Context context;
    private final BleDiscovery bleDiscovery = new BleDiscovery();

    public BluetoothDiscoveryDataSource(Context context) {
        this.context = context.getApplicationContext();
    }

    /**
     * Scans for the TauSync PC beacon (up to 15 s). On the first match, maps the found
     * {@link BluetoothDevice} to a {@link DiscoveredPc} and reports it; on timeout/error reports a
     * failure. Either callback fires exactly once.
     */
    public void startScan(DiscoveryListener listener) {
        bleDiscovery.startScan(context, new BleDiscovery.DiscoveryCallback() {
            @Override
            public void onPcFound(String pcName, BluetoothDevice classicDevice) {
                listener.onPcFound(new DiscoveredPc(pcName, classicDevice.getAddress()));
            }

            @Override
            public void onDiscoveryFailed(String reason) {
                listener.onDiscoveryFailed(reason);
            }
        });
    }

    /**
     * Bonds the PC identified by {@code macAddress}, resolving the string back to a real
     * {@link BluetoothDevice} and saving the address on success (handled by {@link BleDiscovery}).
     */
    public void bond(String macAddress, PairingListener listener) {
        BluetoothAdapter adapter = adapter();
        if (adapter == null) {
            listener.onPairingFailed("Bluetooth is unavailable");
            return;
        }
        BluetoothDevice device;
        try {
            device = adapter.getRemoteDevice(macAddress);
        } catch (IllegalArgumentException e) {
            listener.onPairingFailed("Invalid Bluetooth address: " + macAddress);
            return;
        }
        bleDiscovery.bond(context, device, new BleDiscovery.PairingCallback() {
            @Override
            public void onDevicePaired(BluetoothDevice paired) {
                listener.onPaired(paired.getAddress());
            }

            @Override
            public void onPairingFailed(String reason) {
                listener.onPairingFailed(reason);
            }
        });
    }

    /** Stops an in-progress scan. Safe to call when not scanning. */
    public void stopScan() {
        bleDiscovery.stopScan();
    }

    private static final String PREFS_NAME = "syncdose_bt_prefs";
    private static final String KEY_PC_NAME = "saved_pc_name";

    /** The remembered PC MAC from a previous pairing, or {@code null} on first run. */
    @Nullable
    public String getSavedAddress() {
        return BleDiscovery.getSavedAddress(context);
    }

    /** Forgets the saved PC (used after a lost bond, to force a fresh discovery). */
    public void clearSavedAddress() {
        BleDiscovery.clearSavedAddress(context);
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .edit().remove(KEY_PC_NAME).apply();
    }

    /** Saves the display name of the paired PC alongside the MAC. */
    public void savePcName(String name) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .edit().putString(KEY_PC_NAME, name).apply();
    }

    /** Returns the saved PC display name, or {@code null} if not yet paired. */
    @Nullable
    public String getSavedPcName() {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .getString(KEY_PC_NAME, null);
    }

    @Nullable
    private BluetoothAdapter adapter() {
        BluetoothManager manager =
                (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
        return manager != null ? manager.getAdapter() : null;
    }
}

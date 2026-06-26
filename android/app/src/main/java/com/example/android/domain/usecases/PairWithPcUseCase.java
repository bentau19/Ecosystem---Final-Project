package com.example.android.domain.usecases;

import androidx.annotation.Nullable;

import com.example.android.data.datasource.BluetoothDiscoveryDataSource;
import com.example.android.domain.entities.DiscoveredPc;

/**
 * Domain use case for the first-time Bluetooth pairing flow: discover the TauSync PC over BLE,
 * then bond with it (and remember it for next time).
 *
 * <p>Thin mediator over {@link BluetoothDiscoveryDataSource} — like
 * {@link RefreshLocalStatsUseCase} over {@code SystemDataSource} and {@code BackupTransferUseCase}
 * over {@code BackupDataSource}, it talks to the data source directly (no repository is needed
 * because discovery holds no shared state). Owns the framework-free callback contracts so the
 * ViewModel never depends on the data layer's types.
 */
public class PairWithPcUseCase {

    /** Reports discovery results in framework-free terms. Delivered on a background thread. */
    public interface DiscoveryListener {
        void onPcFound(DiscoveredPc pc);

        void onDiscoveryFailed(String reason);
    }

    /** Reports the bonding outcome. Delivered on the main thread. */
    public interface PairingListener {
        void onPaired(String macAddress);

        void onPairingFailed(String reason);
    }

    private final BluetoothDiscoveryDataSource dataSource;

    public PairWithPcUseCase(BluetoothDiscoveryDataSource dataSource) {
        this.dataSource = dataSource;
    }

    /** Starts scanning for the PC's BLE beacon; {@code listener} is called once on result. */
    public void discover(DiscoveryListener listener) {
        dataSource.startScan(listener);
    }

    /** Stops an in-progress scan. Safe to call when not scanning. */
    public void stopDiscovery() {
        dataSource.stopScan();
    }

    /** Bonds with the PC at {@code macAddress}; saves the address on success. */
    public void pair(String macAddress, PairingListener listener) {
        dataSource.bond(macAddress, listener);
    }

    /** The remembered PC MAC from a previous pairing, or {@code null} on first run. */
    @Nullable
    public String savedAddress() {
        return dataSource.getSavedAddress();
    }

    /** Forgets the saved PC (used after a lost bond, to force a fresh discovery). */
    public void clearSaved() {
        dataSource.clearSavedAddress();
    }

    /** Saves the display name of the paired PC. */
    public void savePcName(String name) {
        dataSource.savePcName(name);
    }

    /** Returns the saved PC display name, or {@code null} if not yet paired. */
    @Nullable
    public String savedPcName() {
        return dataSource.getSavedPcName();
    }
}

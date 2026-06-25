package com.example.android.domain.entities;

/**
 * Entity representing a TauSync PC discovered over Bluetooth LE.
 *
 * <p>Carries only what the domain and UI need — the display {@code name} and the Bluetooth
 * Classic {@code macAddress} (a plain string) — so the Android {@code BluetoothDevice} framework
 * type stays confined to the data layer ({@code BluetoothDiscoveryDataSource}) and never leaks
 * up into the domain or UI. Bonding later takes the MAC string back down, where the data layer
 * resolves it to a real device.
 */
public class DiscoveredPc {
    private final String name;
    private final String macAddress;

    public DiscoveredPc(String name, String macAddress) {
        this.name = name;
        this.macAddress = macAddress;
    }

    public String getName() { return name; }

    public String getMacAddress() { return macAddress; }
}

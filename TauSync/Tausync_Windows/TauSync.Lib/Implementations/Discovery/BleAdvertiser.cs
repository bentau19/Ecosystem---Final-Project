using System;
using System.Threading.Tasks;
using TauSync.Core;
using Windows.Devices.Bluetooth;
using Windows.Devices.Bluetooth.GenericAttributeProfile;

namespace TauSync.Implementations.Discovery
{
    /// <summary>
    /// Advertises a BLE GATT service beacon so a nearby Android device can discover this
    /// Windows PC by UUID without knowing its Bluetooth Classic MAC address in advance.
    ///
    /// <para>Used only for first-time pairing. Once the Android side has saved the Classic
    /// MAC address, BLE advertising is not needed again (unless the bond is lost).</para>
    ///
    /// <para>The service is non-connectable — Android reads the UUID from the advertisement
    /// packet alone without opening a GATT connection. All data traffic runs on RFCOMM Classic,
    /// not BLE.</para>
    ///
    /// <para>If the hardware does not support BLE peripheral mode, <see cref="StartAsync"/>
    /// returns without throwing and <see cref="IsAdvertising"/> stays false. The caller falls
    /// back to manual MAC-address entry.</para>
    /// </summary>
    public sealed class BleAdvertiser : IDisposable
    {
        private GattServiceProvider? _serviceProvider;
        private bool _advertising;
        private bool _disposed;

        /// <summary>True while BLE advertising is active.</summary>
        public bool IsAdvertising => _advertising && !_disposed;

        /// <summary>
        /// Starts BLE advertising. Returns without throwing if the hardware does not support
        /// BLE peripheral mode — <see cref="IsAdvertising"/> will be false in that case.
        /// </summary>
        /// <exception cref="InvalidOperationException">
        /// GATT service provider creation fails for a reason other than hardware absence.
        /// </exception>
        public async Task StartAsync()
        {
            if (_advertising || _disposed) return;

            var btAdapter = await BluetoothAdapter.GetDefaultAsync().AsTask().ConfigureAwait(false);
            if (btAdapter == null || !btAdapter.IsPeripheralRoleSupported)
                return; // no BLE peripheral support — caller falls back to manual entry

            var result = await GattServiceProvider
                .CreateAsync(CoreConfig.BleServiceUuid)
                .AsTask().ConfigureAwait(false);

            if (result.Error != BluetoothError.Success)
                throw new InvalidOperationException($"GATT service create failed: {result.Error}");

            _serviceProvider = result.ServiceProvider;
            _serviceProvider.StartAdvertising(new GattServiceProviderAdvertisingParameters
            {
                IsDiscoverable = true,
                IsConnectable  = false // Android only needs to see the UUID, no GATT connection
            });

            _advertising = true;
        }

        /// <summary>Stops BLE advertising. Safe to call when not advertising or already stopped.</summary>
        public void Stop()
        {
            if (!_advertising) return;
            _advertising = false;
            try { _serviceProvider?.StopAdvertising(); } catch { }
            _serviceProvider = null;
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            Stop();
        }
    }
}

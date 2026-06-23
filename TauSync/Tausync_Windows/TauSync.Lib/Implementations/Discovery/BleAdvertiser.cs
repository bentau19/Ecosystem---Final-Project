using System;
using System.Text;
using System.Threading.Tasks;
using TauSync.Core;
using Windows.Devices.Bluetooth;
using Windows.Devices.Bluetooth.Advertisement;
using Windows.Storage.Streams;

namespace TauSync.Implementations.Discovery
{
    /// <summary>
    /// Advertises a connectionless BLE beacon carrying TauSync's service UUID so a nearby Android
    /// device can discover this Windows PC by UUID without knowing its Bluetooth Classic MAC in
    /// advance.
    ///
    /// <para>Used only for first-time pairing. Once the Android side has saved the Classic MAC,
    /// advertising is not needed again (unless the bond is lost). All data traffic runs on RFCOMM
    /// Classic, not BLE.</para>
    ///
    /// <para>Uses <see cref="BluetoothLEAdvertisementPublisher"/> with manufacturer-specific data
    /// (company id <see cref="CoreConfig.BleBeaconCompanyId"/>, payload
    /// <see cref="CoreConfig.BleBeaconPayload"/>), which Android matches with
    /// <c>ScanFilter.setManufacturerData(...)</c>. A 128-bit service UUID cannot be used: WinRT legacy
    /// advertising rejects it (E_INVALIDARG on Start), and extended advertising is not seen by
    /// Android's <c>CompanionDeviceManager</c> scan. Manufacturer data works in legacy advertising on
    /// both sides.</para>
    ///
    /// <para>If the radio cannot advertise, the publisher transitions to
    /// <see cref="BluetoothLEAdvertisementPublisherStatus.Aborted"/> and <see cref="IsAdvertising"/>
    /// goes false — the caller falls back to manual MAC-address entry. No exception is thrown.</para>
    /// </summary>
    public sealed class BleAdvertiser : IDisposable
    {
        private BluetoothLEAdvertisementPublisher? _publisher;
        private bool _advertising;
        private bool _disposed;

        /// <summary>True while BLE advertising is active (cleared if the radio aborts it).</summary>
        public bool IsAdvertising => _advertising && !_disposed;

        /// <summary>
        /// Starts advertising the TauSync service UUID. Returns immediately; the radio brings the
        /// advertisement up asynchronously. Safe to call when already advertising or disposed.
        /// Does not throw on unsupported hardware — <see cref="IsAdvertising"/> reflects the result.
        /// </summary>
        public async Task StartAsync()
        {
            if (_advertising || _disposed)
                return;

            byte[] payload = await BuildBeaconPayloadAsync().ConfigureAwait(false);

            var publisher = new BluetoothLEAdvertisementPublisher();
            var writer = new DataWriter();
            writer.WriteBytes(payload);
            publisher.Advertisement.ManufacturerData.Add(
                new BluetoothLEManufacturerData(CoreConfig.BleBeaconCompanyId, writer.DetachBuffer()));

            // Clear the flag if the system aborts the advertisement (e.g. no peripheral support),
            // so IsAdvertising honestly reports failure and the caller can fall back.
            publisher.StatusChanged += (sender, args) =>
            {
                if (args.Status == BluetoothLEAdvertisementPublisherStatus.Aborted)
                    _advertising = false;
            };

            _publisher = publisher;
            _advertising = true;
            publisher.Start();
        }

        /// <summary>
        /// Builds the beacon payload: the "TAUS" magic, this PC's 6-byte Bluetooth Classic (BR/EDR)
        /// address (most-significant byte first), then the PC name (UTF-8, truncated). The phone reads
        /// the MAC back and bonds/connects that Classic device — the BLE-advertised address is a
        /// privacy address that cannot be used for RFCOMM — and shows the name in its confirm dialog.
        /// On failure the MAC bytes stay zero and the phone falls back.
        /// </summary>
        private static async Task<byte[]> BuildBeaconPayloadAsync()
        {
            byte[] magic = CoreConfig.BleBeaconPayload;
            byte[] mac = new byte[6];
            try
            {
                var adapter = await BluetoothAdapter.GetDefaultAsync().AsTask().ConfigureAwait(false);
                if (adapter != null)
                {
                    ulong address = adapter.BluetoothAddress;
                    for (int i = 0; i < 6; i++)
                        mac[i] = (byte)((address >> (8 * (5 - i))) & 0xFF);
                }
            }
            catch { /* leave MAC zero — phone falls back to manual entry */ }

            byte[] nameBytes = Encoding.UTF8.GetBytes(Environment.MachineName ?? "PC");
            int nameLen = Math.Min(nameBytes.Length, CoreConfig.BleBeaconMaxNameBytes);

            byte[] payload = new byte[magic.Length + mac.Length + nameLen];
            Array.Copy(magic, 0, payload, 0, magic.Length);
            Array.Copy(mac, 0, payload, magic.Length, mac.Length);
            Array.Copy(nameBytes, 0, payload, magic.Length + mac.Length, nameLen);
            return payload;
        }

        /// <summary>Stops BLE advertising. Safe to call when not advertising or already stopped.</summary>
        public void Stop()
        {
            if (_publisher == null)
                return;
            _advertising = false;
            try { _publisher.Stop(); } catch { }
            _publisher = null;
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            Stop();
        }
    }
}

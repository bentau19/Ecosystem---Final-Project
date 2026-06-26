using System.Text;
using TauSync.Core;
using TauSync.Implementations.Protocol;
using TauSync.Implementations.Transport;

// Manual hardware test for Phase 1 (see Bluetooth_Transport_Plan.md "Test after Phase 1").
// Windows is always the RFCOMM server: run this first, then run the Android counterpart
// (BluetoothTransportManualTest) pointed at this PC's paired Bluetooth address.
//
// Prerequisites:
//   1. Bluetooth must be on and this PC must already be paired with the Android device
//      (Settings > Bluetooth & devices > Add device) before running this.
//   2. The Android device's BluetoothTransportManualTest.WINDOWS_MAC_ADDRESS must be set
//      to this PC's Bluetooth MAC (Settings > Bluetooth & devices > More devices and
//      printer settings, or `Get-PnpDevice -Class Bluetooth` for the radio's own address).

var protocolHandler = new ProtocolHandler();
using var transport = new BluetoothTransport();

transport.OnDataReceived += (_, frame) =>
{
    var (targetId, payload, flags) = protocolHandler.ParseFrame(frame);
    Console.WriteLine($"[RECV] targetId={targetId} flags={flags} text=\"{Encoding.UTF8.GetString(payload)}\"");
};

Console.WriteLine("Advertising RFCOMM service, waiting for Android to connect...");
await transport.Connect(targetId: null);
Console.WriteLine("Connected.");

var frame = protocolHandler.BuildFrame(
    CoreConfig.ControlChannelId,
    Encoding.UTF8.GetBytes("hello from windows"),
    CoreConfig.FlagControl);
await transport.SendRaw(frame);
Console.WriteLine("Sent greeting. Waiting for Android's reply (check [RECV] above)...");

Console.WriteLine("Press Enter to disconnect.");
Console.ReadLine();
transport.Disconnect();

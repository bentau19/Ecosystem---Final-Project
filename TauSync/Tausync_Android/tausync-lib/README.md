# TauSync Android SDK

High-level Android library for real-time, bidirectional communication between Android and Windows (or any TauSync-compatible peer) over a single TCP socket.

Built on top of the TauSync protocol (v3.1) — provides multiplexed named channels, automatic framing, and symmetric connect semantics.

> **Role note:** In the Ecosystem app the Android device always acts as the TCP **client**
> (calls `connectTo(ip)`). The Windows desktop is the TCP server (calls `listen()`).
> The TauSync library supports both roles; the guidance above reflects the expected
> deployment topology, not a library restriction.

## Quick Start

### Server Mode (listen for connections)

```java
TauSync tau = new TauSync();
tau.listen();                                    // blocks until a peer connects
TauSyncStream stream = tau.connect("main");      // open a named channel
String msg = stream.readLine();                  // read a line (UTF-8)
stream.writeString("Hello back!\n");             // send a response
stream.close();
tau.dispose();
```

### Client Mode (connect to a server)

```java
TauSync tau = new TauSync();
tau.connectTo("192.168.1.100");                  // blocks until connected
TauSyncStream stream = tau.connect("main");
stream.writeString("Hello from Android!\n");
String reply = stream.readLine();
stream.close();
tau.dispose();
```

### Multiple Channels on the Same Socket

```java
TauSync tau = new TauSync();
tau.connectTo("192.168.1.100");

// Open several named channels — all multiplex over the same TCP connection
TauSyncStream chat    = tau.connect("chat");
TauSyncStream files   = tau.connect("files");
TauSyncStream control = tau.connect("control");
```

### Multiple Managers (Independent ID Spaces)

```java
TauSync tau = new TauSync();
tau.connectTo("192.168.1.100");

TauSync manager2 = tau.newManager();  // shares the same socket

TauSyncStream s1 = tau.connect("channel_a");
TauSyncStream s2 = manager2.connect("channel_b");
```

## Bluetooth & Hybrid Mode

TauSync can run over **Bluetooth** instead of Wi‑Fi, so the two devices no longer need to share a
network (no router, NAT, captive portal, or firewall in the way). Android is always the Bluetooth
**client**; the Windows PC is the Bluetooth **server**.

**Hybrid mode** uses both links: **Bluetooth is always on** (control traffic + small messages) and
**Wi‑Fi is brought up automatically and only when a large payload needs the speed** (a file), then
dropped after it sits idle. The PC's Wi‑Fi IP is discovered over Bluetooth — you never type it.

Routing is automatic, decided by which method you call:

| You call | Travels over |
|----------|--------------|
| `writeString(...)`, small `write(...)` | **Bluetooth** |
| `writeFile(...)` | **Wi‑Fi** (falls back to Bluetooth if Wi‑Fi can't be established) |

### Permissions

Add to your app's `AndroidManifest.xml` and request the runtime ones (API 31+) before connecting:

```xml
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
<uses-permission android:name="android.permission.BLUETOOTH_SCAN"
    android:usesPermissionFlags="neverForLocation" />
```

### Connect when you already know the PC's MAC

```java
// All TauSync calls block — run on a background thread.
TauSync tau = new TauSync();
tau.connectHybrid(context, "AA:BB:CC:DD:EE:FF");   // BT connect + handshake

TauSyncStream stream = tau.connect("main");
stream.writeString("hello over bluetooth\n");       // → Bluetooth
stream.writeFile("/sdcard/DCIM/photo.jpg");          // → Wi‑Fi (automatic)
stream.close();

String pcWifiIp = tau.getPeerWifiIp();  // discovered over BT, e.g. "192.168.1.50"
boolean wifiUp  = tau.isWifiActive();   // true only while a large transfer keeps Wi‑Fi up
tau.dispose();
```

### First‑time pairing — discover the PC over BLE (no MAC typing)

The first time you don't know the PC's MAC. The PC advertises a BLE beacon carrying its **name** and
its Bluetooth MAC. `BleDiscovery` scans for it, hands you the name so you can show your own confirm
dialog, then **bonds and remembers the MAC** so later launches skip discovery entirely.

```java
BleDiscovery bleDiscovery = new BleDiscovery();

// 1. Returning launch? Use the saved MAC directly — no scan, no dialog.
String saved = BleDiscovery.getSavedAddress(context);
if (saved != null) {
    tau.connectHybrid(context, saved);   // (background thread)
    return;
}

// 2. First launch: scan for the PC's beacon, then ask the user.
bleDiscovery.startScan(activity, new BleDiscovery.DiscoveryCallback() {
    @Override public void onPcFound(String pcName, BluetoothDevice pc) {
        runOnUiThread(() -> new AlertDialog.Builder(activity)
            .setTitle("TauSync PC found")
            .setMessage("Connect to \"" + pcName + "\" (" + pc.getAddress() + ")?")
            .setPositiveButton("Connect", (d, w) -> pairAndConnect(pc))
            .setNegativeButton("Cancel", null)
            .show());
    }
    @Override public void onDiscoveryFailed(String reason) {
        Log.w(TAG, "No TauSync PC found nearby: " + reason);
    }
});

// 3. Bond over Classic Bluetooth (+ save the MAC), then connect.
void pairAndConnect(BluetoothDevice pc) {
    bleDiscovery.bond(context, pc, new BleDiscovery.PairingCallback() {
        @Override public void onDevicePaired(BluetoothDevice paired) {
            // paired + bonded + MAC saved. Connect on a background thread.
            backgroundExecutor.execute(() ->
                tau.connectHybrid(context, paired.getAddress()));
        }
        @Override public void onPairingFailed(String reason) {
            Log.w(TAG, "Pairing failed: " + reason);
        }
    });
}
```

**What the user sees the first time:** phone scans → *your* "Found <PC name>?" dialog → the PC pops a
**"Phone wants to connect — Accept / Reject"** prompt → connected. After that, **both sides remember
each other and reconnect silently** (the saved MAC skips the phone dialog; the PC skips its prompt).

> **Bond lost** (user unpaired the PC in system settings): `connectHybrid` throws, with
> `BluetoothTransport.BondLostException` somewhere in the cause chain. Catch it, call
> `BleDiscovery.clearSavedAddress(context)`, and re‑run `startScan` to re‑pair.

> Call `bleDiscovery.stopScan()` in your Activity's `onDestroy()` to end a scan that's still running.

### `BleDiscovery` API

| Method | Description |
|--------|-------------|
| `startScan(Context, DiscoveryCallback)` | Scan for the PC beacon (15 s). `onPcFound(name, device)` fires on the first match; `onDiscoveryFailed(reason)` on timeout/error. |
| `bond(Context, BluetoothDevice, PairingCallback)` | Pair over Classic Bluetooth, save the MAC, then `onDevicePaired(device)`. |
| `stopScan()` | Stop an in‑progress scan. |
| `getSavedAddress(Context)` *(static)* | The remembered PC MAC, or `null`. |
| `clearSavedAddress(Context)` *(static)* | Forget the saved PC (use after a bond loss). |

## Threading

All TauSync operations are **blocking** and must be called from a background thread. On Android, use `Dispatchers.IO` (Kotlin coroutines) or `Executors.newSingleThreadExecutor()`:

```kotlin
lifecycleScope.launch(Dispatchers.IO) {
    val tau = TauSync()
    tau.connectTo("192.168.1.100")
    val stream = tau.connect("main")
    stream.writeString("Hello!\n")
    val reply = stream.readLine()
    withContext(Dispatchers.Main) {
        textView.text = reply
    }
    stream.close()
    tau.dispose()
}
```

## API Reference

### `TauSync` — Main Entry Point


| Method                                 | Description                                              |
| -------------------------------------- | -------------------------------------------------------- |
| `listen()`                             | Start server mode. Blocks until a peer connects.         |
| `connectTo(String ip)`                 | Connect to a server. Blocks until connected.             |
| `connect(String word)`                 | Open a named channel (30s timeout). Blocks until paired. |
| `connect(String word, int timeoutSec)` | Open a channel with custom timeout.                      |
| `isConnected()`                        | Returns `true` if the transport layer is active.         |
| `getPeerWaitingWords()`                | `List<String>` snapshot of words the peer has REQ'd that we have not paired yet. |
| `newManager()`                         | Creates another TauSync sharing the same socket.         |
| `connectHybrid(Context, String mac)`   | Connect over Bluetooth (hybrid BT + lazy Wi‑Fi). Blocks until the BT link + handshake are up. |
| `getPeerWifiIp()`                       | The peer's Wi‑Fi IP discovered over Bluetooth, or `null`. |
| `isWifiActive()`                       | `true` while the lazy Wi‑Fi link is currently up (e.g. during a file transfer). |
| `disconnect()`                         | Closes the transport but keeps this instance usable — you can `connectTo()`/`connectHybrid()` again afterward (unlike `dispose()`). |
| `dispose()`                            | Releases the underlying ConnectionManager. Idempotent.   |


**Role protection**: Once `listen()` is called, `connectTo()` is forbidden (and vice versa). The underlying TCP transport is a process-wide singleton.

### `TauSyncStream` — Bidirectional Channel

#### Read Operations


| Method                    | Returns            | Description                                                                      |
| ------------------------- | ------------------ | -------------------------------------------------------------------------------- |
| `readLine()`              | `String` or `null` | Reads until `\n`. Returns without the newline. `null` on EOF.                    |
| `readLine(int maxLength)` | `String` or `null` | Same, with a custom safety limit.                                                |
| `readExactly(int count)`  | `byte[]`           | Blocks until exactly N bytes arrive. Throws `EOFException` if stream ends early. |
| `readAll()`               | `byte[]`           | Reads all remaining data until EOF.                                              |
| `readAll(int chunkSize)`  | `byte[]`           | Same, with custom buffer size.                                                   |
| `getInputStream()`        | `InputStream`      | Raw InputStream for advanced use.                                                |


#### Write Operations


| Method                     | Returns        | Description                                         |
| -------------------------- | -------------- | --------------------------------------------------- |
| `write(byte[] data)`       | `int`          | Writes raw bytes. Returns count written.            |
| `writeString(String text)` | `int`          | Encodes as UTF-8 and writes. Returns bytes written. |
| `getOutputStream()`        | `OutputStream` | Raw OutputStream for advanced use.                  |


#### File Transfer


| Method                                                | Returns | Description                                           |
| ----------------------------------------------------- | ------- | ----------------------------------------------------- |
| `writeFile(String path)`                              | `long`  | Streams a file into the channel (64KB chunks).        |
| `writeFile(String path, int chunkSize)`               | `long`  | Same, with custom chunk size.                         |
| `readToFile(String path, long length)`                | `long`  | Receives exactly `length` bytes and writes to a file. |
| `readToFile(String path, long length, int chunkSize)` | `long`  | Same, with custom chunk size.                         |


#### Lifecycle


| Method         | Description                                             |
| -------------- | ------------------------------------------------------- |
| `close()`      | Sends FIN to peer, releases the channel ID. Idempotent. |
| `getLocalId()` | Returns the TPack ID assigned to this channel.          |


## File Transfer Example

### Sender (Server)

```java
TauSync tau = new TauSync();
tau.listen();
TauSyncStream stream = tau.connect("photo_transfer");

File photo = new File("/sdcard/DCIM/photo.jpg");
stream.writeString(photo.length() + "\n");       // send file size first
long sent = stream.writeFile(photo.getAbsolutePath());
stream.close();
tau.dispose();
```

### Receiver (Client)

```java
TauSync tau = new TauSync();
tau.connectTo("192.168.1.100");
TauSyncStream stream = tau.connect("photo_transfer");

long size = Long.parseLong(stream.readLine());   // read file size
stream.readToFile("/sdcard/Download/photo.jpg", size);
stream.close();
tau.dispose();
```

## Error Handling

All methods throw standard Java exceptions:

- `IllegalStateException` — wrong lifecycle (e.g. `connect()` before `listen()`)
- `IllegalArgumentException` — invalid parameters (null, blank, negative)
- `IOException` / `EOFException` — network or stream errors
- `RuntimeException` — wraps checked exceptions from the underlying protocol

## Architecture

```
┌──────────────────────────────────┐
│         Your Application         │
├──────────────────────────────────┤
│     TauSync  (SDK entry point)   │  ← you are here
│     TauSyncStream  (channels)    │
├──────────────────────────────────┤
│     ConnectionManager            │  multiplexing + handshake
│     ConnectionContext             │  ID management + routing
│     ProtocolHandler              │  TPack framing
├──────────────────────────────────┤
│     SocketTransport              │  TCP socket
└──────────────────────────────────┘
```

## Requirements

- **Min SDK**: 21 (Android 5.0)
- **Dependencies**: Gson (for protocol handshake JSON)
- **Permissions**:
  - Wi‑Fi mode: `android.permission.INTERNET`
  - Bluetooth/hybrid mode (API 31+, request at runtime): `android.permission.BLUETOOTH_CONNECT`,
    `android.permission.BLUETOOTH_SCAN`


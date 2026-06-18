# TauSync — Bluetooth Transport

## Motivation

TauSync currently runs exclusively over TCP/Wi-Fi. This means both devices must share the same network — the same router, the same subnet, and no firewall blocking peer-to-peer traffic. In practice this is a significant constraint: corporate networks, hotel Wi-Fi, captive portals, and mobile hotspots regularly prevent device-to-device TCP connections. TauSync silently fails in all of these environments.

Adding Bluetooth Classic (RFCOMM) as a second transport layer solves this at the root. Bluetooth is a direct physical link between devices — no router, no NAT traversal, no firewall. Once two devices are paired, they can establish a TauSync session regardless of what network they are (or are not) on.

### Why Bluetooth Classic and not BLE

Bluetooth Low Energy is designed for small, infrequent payloads (sensor readings, beacons). Its MTU cap (~512 bytes) and connection-oriented GATT model are fundamentally mismatched with TauSync's streaming multiplexed protocol. Bluetooth Classic RFCOMM provides a full-duplex byte stream — the same abstraction as a TCP socket — which means the entire TauSync protocol stack above the transport layer requires no changes.

### Why this fits the existing architecture

`ITransport` (C#) and the transport interface (Android) were already designed as transport-agnostic interfaces. `SocketTransport` is one implementation; `BluetoothTransport` will be another. The protocol, multiplexing, and SDK layers are completely unaware of what carries the bytes. This is a Layer 1 addition, not a protocol change.

### What it unlocks

- **Connectivity independence** — sync works anywhere two devices are within ~10 meters, regardless of network.
- **Simpler connection UX** — Bluetooth pairing replaces manual IP entry. After the first pair, reconnection is automatic.
- **Fallback resilience** — with both transports available, each channel can use the transport best suited for its data size.

### Accepted tradeoff

Bluetooth Classic throughput is roughly 1–3 Mbps effective, compared to tens or hundreds of Mbps over Wi-Fi. Large file transfers will be noticeably slower. This is acceptable: the Bluetooth transport is the "always works" path, not the "maximum performance" path.

---

## Implementation Plan

---

## 1. High-Level Architecture

After this feature is complete, a TauSync session can run over three configurations:

| Mode | Transport | When used |
|------|-----------|-----------|
| Wi-Fi only (existing) | `SocketTransport` | No Bluetooth available, or user has not paired |
| Bluetooth only | `BluetoothTransport` | No shared Wi-Fi network |
| Hybrid | `BluetoothTransport` + `SocketTransport` | Both available — BT bootstraps Wi-Fi |

The protocol stack does not change. `BluetoothTransport` is a new implementation of `ITransport` (C#) / the existing transport interface (Android). Everything at Layer 2 and above is unaffected.

The app works with three `ConnectionManager` configurations. The caller chooses which one to use for each channel:

- **`EcoConnectionManager`** — a `ConnectionManager` wrapping `BluetoothTransport` only. Reliable everywhere, lower throughput.
- **`PerformanceConnectionManager`** — a `ConnectionManager` wrapping `SocketTransport` only. Fast, requires shared network.
- **`HybridConnectionManager`** — owns the full session setup (BLE pairing → BT Classic session handshake → Wi-Fi bootstrap via session token). After setup it exposes both an `EcoConnectionManager` and a `PerformanceConnectionManager` to the app. The app explicitly picks which one to use per channel based on the `HYBRID_SMALL_THRESHOLD_BYTES` constant as a guide. `HybridConnectionManager` does not auto-route individual frames.

Note: `EcoConnectionManager` and `PerformanceConnectionManager` are not separate classes — they are `ConnectionManager` instances constructed with different `ITransport` implementations and exposed via factory methods on the SDK.

---

## 2. Full Connection Flow

### 2.1 Happy Path (Hybrid — BT + Wi-Fi)

```
Windows (server)                             Android (client)
────────────────                             ────────────────
HybridConnectionManager.StartAsync():
  BleAdvertiser.Start()
    └─ BLE GATT peripheral advertising
       TauSync BLE_SERVICE_UUID
  BluetoothTransport.StartListening()
    └─ RFCOMM listener waiting
  SocketTransport.StartListening()
    └─ TCP listener waiting on DEFAULT_PORT

                                             First launch — BleDiscovery.startDiscovery()
                                             ← BLE advertisement found (BluetoothLeDeviceFilter
                                               matching BLE_SERVICE_UUID)
                                             OS shows native pairing popup
                                             User taps "Connect"
                                             device.getAddress() saved to SharedPreferences
                                             (future launches skip BleDiscovery entirely)

                          ←── RFCOMM socket opens ───────────
BT Session Handshake (control channel, TargetID=0 only — no meeting word):
  Server → Client: {"MagicBytes": 1414743891}
  Client → Server: {"MagicBytes": 1414743891}
  Both sides confirm peer is a valid TauSync endpoint.

Server generates sessionToken (UUID v4)
ConnectionContext.setSessionToken(token)
Server sends SESSION_INFO on TargetID=0:
  {"Type":"SESSION_INFO",
   "SessionToken":"<token>",
   "WifiHost":"192.168.x.x",
   "WifiPort":5000}
                          ───── SESSION_INFO ─────────────→
                                             Client stores token:
                                             ConnectionContext.setSessionToken(token)
                                             Client opens TCP to WifiHost:WifiPort

SocketTransport already listening on DEFAULT_PORT
                          ←── TCP socket opens ──────────────
Client sends SESSION_JOIN on Wi-Fi TargetID=0:
  {"MagicBytes":1414743891,
   "Type":"SESSION_JOIN",
   "SessionToken":"<token>"}
                          ───── SESSION_JOIN ──────────────→
Server verifies token == ConnectionContext.getSessionToken()
Server sends SESSION_JOIN_ACK:
  {"Type":"SESSION_JOIN_ACK"}
                          ←── SESSION_JOIN_ACK ────────────

HybridConnectionManager on both sides now holds both transports.
App uses getEcoManager() for small/control channels (BT).
App uses getPerformanceManager() for large transfers (Wi-Fi).
```

### 2.2 Returning Launch (Hybrid — Device Already Paired)

Identical to 2.1 except BleDiscovery is skipped entirely. Android reads the saved device address from SharedPreferences and calls `BluetoothTransport.connect(savedAddress)` directly. BleAdvertiser still runs on Windows because it is cheap and harmless.

### 2.3 Bond Lost (Device Unpaired from System Settings)

`BluetoothTransport.connect()` checks `device.getBondState() == BOND_BONDED` before attempting RFCOMM. If the bond is gone, it triggers `BleDiscovery.startDiscovery()` automatically to re-pair, then retries the RFCOMM connect after the new bond is established. The saved address in SharedPreferences is updated with the result.

### 2.4 Fallback Path (Wi-Fi Only — No Changes)

If Bluetooth is unavailable or the user never paired, the app uses the existing `ConnectionManager` directly with `SocketTransport`. The user enters an IP address as today. Zero changes to this path.

---

## 3. Protocol Changes

### 3.1 New CoreConfig Constants

Add to `CoreConfig.java` (Android) and `Core.cs` (Windows). All values must match across platforms.

```java
// Android — CoreConfig.java additions
public static final String BLE_SERVICE_UUID    = "12345678-1234-5678-1234-56789abcde01";
public static final String RFCOMM_SERVICE_UUID = "12345678-1234-5678-1234-56789abcde02";
public static final int    BT_CONNECT_TIMEOUT_MS        = 15_000;
public static final int    SESSION_JOIN_ACK_TIMEOUT_MS  = 10_000;
public static final int    HYBRID_SMALL_THRESHOLD_BYTES = 65_536; // 64 KB — configurable
```

```csharp
// Windows — Core.cs additions
public static readonly Guid BleServiceUuid    = new Guid("12345678-1234-5678-1234-56789abcde01");
public static readonly Guid RfcommServiceUuid = new Guid("12345678-1234-5678-1234-56789abcde02");
public const int BtConnectTimeoutMs       = 15_000;
public const int SessionJoinAckTimeoutMs  = 10_000;
public const int HybridSmallThresholdBytes = 65_536; // 64 KB — configurable
```

`HYBRID_SMALL_THRESHOLD_BYTES` is intentionally a constant (not hardcoded) so it can be tuned without touching logic. The app reads it as a guide when deciding which manager to open a channel on — `HybridConnectionManager` itself never routes on this value.

### 3.2 New Control Channel Message Types

The control channel (TargetID = 0) already carries handshake JSON. Four new message types are added. All are JSON objects sent on TargetID = 0.

**BT_MAGIC** — exchanged on both sides immediately after RFCOMM socket opens, before any other message. Confirms both peers are TauSync endpoints. No meeting word involved.
```json
{"MagicBytes": 1414743891}
```

**SESSION_INFO** — Server → Client, sent over BT after BT_MAGIC exchange succeeds.
```json
{
  "Type": "SESSION_INFO",
  "SessionToken": "<uuid-v4-string>",
  "WifiHost": "192.168.1.100",
  "WifiPort": 5000
}
```

**SESSION_JOIN** — Client → Server, sent over the Wi-Fi TCP control channel as the very first frame after TCP connects.
```json
{
  "MagicBytes": 1414743891,
  "Type": "SESSION_JOIN",
  "SessionToken": "<uuid-v4-string>"
}
```
`MagicBytes` is included so the server's existing control-channel dispatcher recognizes it as a valid TauSync frame before branching on `Type`.

**SESSION_JOIN_ACK** — Server → Client, sent over Wi-Fi after successful token verification.
```json
{"Type": "SESSION_JOIN_ACK"}
```

If the token does not match, the server closes the TCP connection immediately with no response.

### 3.3 Session Token Lifecycle

- Generated server-side as `UUID.randomUUID().toString()` / `Guid.NewGuid().ToString()` immediately after BT_MAGIC exchange succeeds.
- Stored in `ConnectionContext.sessionToken` (nullable string, initially null).
- Cleared by `ConnectionContext.reset()` — but see Section 6.3 for when `reset()` is actually called in Hybrid mode.
- Single-use for session establishment. Once Wi-Fi joins, the token remains stored but is not reused.

### 3.4 Existing Handshake is Untouched

The regular `ConnectionManager` meeting-word handshake (used for app-level channels on both BT and Wi-Fi) is unchanged. The BT session handshake described above is a separate flow handled entirely by `HybridConnectionManager`. Existing handshake messages have no `Type` field, so the new SESSION_JOIN branch in the dispatcher is never triggered by them.

---

## 4. New Files to Create

### Windows (C#)

| File | Purpose |
|------|---------|
| `TauSync.Lib/Implementations/Transport/BluetoothTransport.cs` | RFCOMM ITransport implementation |
| `TauSync.Lib/Implementations/Discovery/BleAdvertiser.cs` | BLE GATT peripheral, advertises TauSync BLE_SERVICE_UUID |
| `TauSync.Lib/Implementations/Management/HybridConnectionManager.cs` | Session orchestrator, starts both listeners, exposes eco/performance managers |

### Android (Java)

| File | Purpose |
|------|---------|
| `tausync-lib/implementations/transport/BluetoothTransport.java` | RFCOMM ITransport implementation |
| `tausync-lib/implementations/discovery/BleDiscovery.java` | CompanionDeviceManager + bond-loss re-pairing |
| `tausync-lib/implementations/management/HybridConnectionManager.java` | Session orchestrator |

---

## 5. Files to Modify

| File | Change |
|------|--------|
| `CoreConfig.java` / `Core.cs` | Add new constants (Section 3.1) |
| `ConnectionContext.java` / `ConnectionContext.cs` | Add `sessionToken` field + getter/setter + `activeTransportCount` for safe reset (Section 6.3) |
| `ConnectionManager.java` / `ConnectionManager.cs` | Add `startBtSession()` / `joinBtSession()` and `joinSession(token)` methods; add control-message hook for SESSION_JOIN |
| `ITransport.cs` / transport interface | Add `TransportType` property (enum: WiFi, Bluetooth) |
| `AndroidManifest.xml` | Add BT permissions |
| `TauSync.java` (SDK) | Expose factory methods for hybrid/eco/performance managers |

---

## 6. Detailed Implementation Guide

Implement in this exact order. Each phase is independently testable before moving to the next.

---

### Phase 1 — `BluetoothTransport` (both platforms)

This is the core deliverable. Implement it to be structurally identical to `SocketTransport` — same receive loop pattern, same `sendRaw` pattern, same connect/disconnect lifecycle. Read `SocketTransport` carefully before writing `BluetoothTransport`; the only differences are the underlying stream source and connection setup calls.

**`ITransport` addition — `TransportType`**

Before writing `BluetoothTransport`, add this to the interface on both platforms:

```csharp
// C# — ITransport.cs
TransportKind TransportType { get; }
public enum TransportKind { WiFi, Bluetooth }
```
```java
// Java — add to transport interface
TransportKind getTransportType();
enum TransportKind { WIFI, BLUETOOTH }
```

`SocketTransport` returns `WiFi`. `BluetoothTransport` returns `Bluetooth`. `HybridConnectionManager` uses this to identify which transport is which.

**Windows — `BluetoothTransport.cs`**

Fields (mirror `SocketTransport`):
```csharp
private StreamSocket? _socket;
private DataWriter? _writer;
private DataReader? _reader;
private CancellationTokenSource? _receiveCts;
private readonly SemaphoreSlim _sendLock = new SemaphoreSlim(1, 1);
private bool _isConnected;
private bool _disposed;
```

Server-mode `StartListeningAsync()` — Windows is always server for Bluetooth:
```csharp
var serviceProvider = await RfcommServiceProvider.CreateAsync(
    RfcommServiceId.FromUuid(CoreConfig.RfcommServiceUuid));

var listener = new StreamSocketListener();
listener.ConnectionReceived += OnConnectionReceived;
await listener.BindServiceNameAsync(
    serviceProvider.ServiceId.AsString(),
    SocketProtectionLevel.BluetoothEncryptionAllowNullAuthentication);

serviceProvider.StartAdvertising(listener, true); // true = include SDP record so Android can find channel by UUID
```

`OnConnectionReceived`: store the `StreamSocket`, set `_isConnected = true`, notify `ConnectionContext.NotifyTransportConnected()` (Phase 6.3), start the receive loop (copy from `SocketTransport.ReceiveLoopAsync` — identical TPack framing logic).

`SendRawAsync(byte[] data)`: copy from `SocketTransport.SendRawAsync`, swap `NetworkStream.WriteAsync` for `DataWriter.WriteBytes` + `DataWriter.StoreAsync`.

`Disconnect()`: cancel `_receiveCts`, close `_socket`, call `ConnectionContext.Instance.NotifyTransportDisconnected()` (NOT `reset()` directly — see Section 6.3).

**Android — `BluetoothTransport.java`**

Fields (mirror `SocketTransport`):
```java
private BluetoothSocket btSocket;
private InputStream inputStream;
private OutputStream outputStream;
private volatile boolean connected = false;
private volatile boolean disposed  = false;
private Thread receiveThread;
private final Semaphore sendLock = new Semaphore(1);
```

Client-mode `connect(String deviceAddress)`:
```java
// API 31+: use BluetoothManager.getAdapter() instead of getDefaultAdapter()
BluetoothAdapter adapter = ((BluetoothManager)
    context.getSystemService(Context.BLUETOOTH_SERVICE)).getAdapter();

BluetoothDevice device = adapter.getRemoteDevice(deviceAddress);

// Bond check — triggers re-pairing if bond lost (see Section 2.3)
if (device.getBondState() != BluetoothDevice.BOND_BONDED) {
    bleDiscovery.startDiscovery(activity, pairingCallback); // blocks until re-paired
    device = adapter.getRemoteDevice(/* updated address from pairingCallback */);
}

btSocket = device.createRfcommSocketToServiceRecord(
    UUID.fromString(CoreConfig.RFCOMM_SERVICE_UUID));
// SDP lookup uses RFCOMM_SERVICE_UUID to find the correct RFCOMM channel on the Windows side.
// This is why both platforms MUST use the same UUID — without it, connect() throws.

adapter.cancelDiscovery(); // always cancel active BT discovery before connect; it slows RFCOMM
btSocket.connect();        // blocks — call on background thread; wrap in Future with BT_CONNECT_TIMEOUT_MS
inputStream  = btSocket.getInputStream();
outputStream = btSocket.getOutputStream();
connected = true;
ConnectionContext.getInstance().notifyTransportConnected();
startReceiveLoop();
```

`startReceiveLoop()`: copy from `SocketTransport.receiveLoop()` — TPack framing is identical. Only difference: read from `btSocket.getInputStream()` instead of TCP socket's stream.

`sendRaw(byte[] data)`: copy from `SocketTransport.sendRaw()` — same semaphore pattern, same output stream write.

`disconnect()`: set `connected = false`, close streams, close `btSocket`, call `ConnectionContext.getInstance().notifyTransportDisconnected()` (NOT `reset()` directly).

**Test after Phase 1:** Write a standalone test that connects `BluetoothTransport` (Windows server + Android client), sends TPack frames both ways, and verifies data arrives intact. Do NOT involve `ConnectionManager` yet — test transport in isolation.

---

### Phase 2 — Session Token + Transport Count in `ConnectionContext`

Add to `ConnectionContext` on both platforms:

```java
// Java
private volatile String sessionToken = null;
private final AtomicInteger activeTransportCount = new AtomicInteger(0);

public void setSessionToken(String token)  { this.sessionToken = token; }
public String getSessionToken()            { return sessionToken; }

public void notifyTransportConnected()     { activeTransportCount.incrementAndGet(); }
public void notifyTransportDisconnected() {
    if (activeTransportCount.decrementAndGet() == 0) {
        reset(); // only reset when the last transport disconnects
    }
}

// In reset() — add:
sessionToken = null;
// activeTransportCount is NOT reset here — it is managed by connect/disconnect calls
```

```csharp
// C#
private volatile string? _sessionToken;
private int _activeTransportCount = 0;

public void SetSessionToken(string token)  => _sessionToken = token;
public string? GetSessionToken()           => _sessionToken;

public void NotifyTransportConnected()     => Interlocked.Increment(ref _activeTransportCount);
public void NotifyTransportDisconnected()
{
    if (Interlocked.Decrement(ref _activeTransportCount) == 0)
        Reset();
}

// In Reset() — add:
_sessionToken = null;
```

This is the fix for the critical bug where one transport disconnecting would destroy the other transport's active channels. By counting active transports, `reset()` only fires when the last one drops — safe for both solo and hybrid use.

**Important:** `SocketTransport.Disconnect()` must also be updated to call `NotifyTransportDisconnected()` instead of `Reset()` directly.

---

### Phase 3 — BT Session Handshake + SESSION_INFO + SESSION_JOIN

This phase wires the two transports into a single session. It adds new methods to `ConnectionManager` and new branches in the control channel dispatcher.

**Step 3a — Add `startBtSession()` to `ConnectionManager` (server side)**

`HybridConnectionManager` calls this after `BluetoothTransport` connects. It runs the BT session handshake on TargetID=0 — no meeting word.

```java
// Java — new method on ConnectionManager (server only)
public String startBtSession() throws IOException {
    // 1. Exchange MagicBytes to confirm peer is TauSync
    byte[] magicPayload = new Gson()
        .toJson(Map.of("MagicBytes", CoreConfig.MAGIC_BYTES))
        .getBytes(StandardCharsets.UTF_8);
    transport.sendRaw(protocolHandler.buildFrame(
        CoreConfig.CONTROL_TARGET_ID, magicPayload, CoreConfig.FLAG_CONTROL)).get();

    // 2. Wait for peer MagicBytes (control channel dispatcher routes TargetID=0 frames here)
    Map<String, Object> peerMagic = waitForControlMessage(BT_CONNECT_TIMEOUT_MS);
    if (!CoreConfig.MAGIC_BYTES.equals(((Double) peerMagic.get("MagicBytes")).intValue()))
        throw new IOException("Peer MagicBytes mismatch");

    // 3. Generate token and send SESSION_INFO
    String token = UUID.randomUUID().toString();
    ConnectionContext.getInstance().setSessionToken(token);
    String wifiHost = NetworkUtils.getLocalWifiIpAddress(); // utility — see note below
    int    wifiPort = CoreConfig.DEFAULT_PORT;
    byte[] infoPayload = new Gson()
        .toJson(Map.of("Type", "SESSION_INFO", "SessionToken", token,
                       "WifiHost", wifiHost, "WifiPort", wifiPort))
        .getBytes(StandardCharsets.UTF_8);
    transport.sendRaw(protocolHandler.buildFrame(
        CoreConfig.CONTROL_TARGET_ID, infoPayload, CoreConfig.FLAG_CONTROL)).get();
    return token;
}
```

`NetworkUtils.getLocalWifiIpAddress()`: enumerate `NetworkInterface.getNetworkInterfaces()`, find the interface that is up, not loopback, not Bluetooth, and has an IPv4 address. Write this once in a shared utility class. Known limitation: on machines with VPN or multiple adapters it may pick the wrong IP — acceptable for now, can be made configurable later.

**Step 3b — Add `joinBtSession()` to `ConnectionManager` (client side)**

```java
// Java — new method on ConnectionManager (client only)
public SessionInfo joinBtSession() throws IOException {
    // 1. Send MagicBytes
    byte[] magicPayload = new Gson()
        .toJson(Map.of("MagicBytes", CoreConfig.MAGIC_BYTES))
        .getBytes(StandardCharsets.UTF_8);
    transport.sendRaw(protocolHandler.buildFrame(
        CoreConfig.CONTROL_TARGET_ID, magicPayload, CoreConfig.FLAG_CONTROL)).get();

    // 2. Wait for peer MagicBytes
    Map<String, Object> peerMagic = waitForControlMessage(BT_CONNECT_TIMEOUT_MS);
    if (!CoreConfig.MAGIC_BYTES.equals(((Double) peerMagic.get("MagicBytes")).intValue()))
        throw new IOException("Peer MagicBytes mismatch");

    // 3. Wait for SESSION_INFO
    Map<String, Object> info = waitForControlMessage(BT_CONNECT_TIMEOUT_MS);
    if (!"SESSION_INFO".equals(info.get("Type")))
        throw new IOException("Expected SESSION_INFO, got: " + info.get("Type"));

    String token    = (String) info.get("SessionToken");
    String wifiHost = (String) info.get("WifiHost");
    int    wifiPort = ((Double) info.get("WifiPort")).intValue();
    ConnectionContext.getInstance().setSessionToken(token);
    return new SessionInfo(token, wifiHost, wifiPort);
}
```

`waitForControlMessage(timeout)`: blocks until a frame arrives on TargetID=0, parses it as JSON, and returns the map. Use a `SynchronousQueue` or `CompletableFuture` that the control channel dispatcher writes into. This is analogous to the existing pending-response pattern already in `ConnectionManager`.

**Step 3c — Add `joinSession(token)` to `ConnectionManager` (Wi-Fi client side)**

```java
// Java — new method on ConnectionManager
public void joinSession(String token) throws IOException {
    byte[] payload = new Gson()
        .toJson(Map.of("MagicBytes", CoreConfig.MAGIC_BYTES,
                       "Type",        "SESSION_JOIN",
                       "SessionToken", token))
        .getBytes(StandardCharsets.UTF_8);
    transport.sendRaw(protocolHandler.buildFrame(
        CoreConfig.CONTROL_TARGET_ID, payload, CoreConfig.FLAG_CONTROL)).get();

    // Wait for SESSION_JOIN_ACK with SESSION_JOIN_ACK_TIMEOUT_MS timeout
    Map<String, Object> ack = waitForControlMessage(CoreConfig.SESSION_JOIN_ACK_TIMEOUT_MS);
    if (!"SESSION_JOIN_ACK".equals(ack.get("Type")))
        throw new IOException("SESSION_JOIN rejected or timed out");
}
```

**Step 3d — Add SESSION_JOIN handler to the control channel dispatcher (server side)**

In the existing control channel frame handler, add a new branch before the existing meeting-word logic:

```java
if ("SESSION_JOIN".equals(parsed.get("Type"))) {
    String incoming = (String) parsed.get("SessionToken");
    String expected = ConnectionContext.getInstance().getSessionToken();
    if (expected == null || !expected.equals(incoming)) {
        transport.disconnect(); // invalid or expired token
        return;
    }
    // Notify HybridConnectionManager via injected callback (see Phase 4)
    if (wifiJoinCallback != null) wifiJoinCallback.run();
    // Send ACK
    byte[] ack = new Gson()
        .toJson(Map.of("Type", "SESSION_JOIN_ACK"))
        .getBytes(StandardCharsets.UTF_8);
    transport.sendRaw(protocolHandler.buildFrame(
        CoreConfig.CONTROL_TARGET_ID, ack, CoreConfig.FLAG_CONTROL)).get();
    return;
}
```

`wifiJoinCallback` is a `Runnable` injected by `HybridConnectionManager` at construction time (see Phase 4). This is how `HybridConnectionManager` learns that Wi-Fi has joined without `ConnectionManager` depending on it.

**Test after Phase 3:** BT connects, BT_MAGIC exchanged, SESSION_INFO received by Android, Wi-Fi TCP connects, SESSION_JOIN sent, ACK received. Verify `ConnectionContext.getSessionToken()` is set on both sides and matches.

---

### Phase 4 — `HybridConnectionManager` (both platforms)

`HybridConnectionManager` is the session orchestrator. It does not extend `ConnectionManager` — it owns two `ConnectionManager` instances, starts both listeners together, and manages the handshake flow between them.

**Callback wiring:** `HybridConnectionManager` injects two callbacks into the inner managers at construction time:
1. Into the BT `ConnectionManager`: a `sessionInfoCallback` that fires when SESSION_INFO arrives (gives Wi-Fi address).
2. Into the Wi-Fi `ConnectionManager`: a `wifiJoinCallback` that fires when SESSION_JOIN is successfully verified.

These callbacks let `HybridConnectionManager` coordinate the flow without creating a circular dependency.

**Android — `HybridConnectionManager.java`:**

```java
public class HybridConnectionManager {

    private final ConnectionManager btManager;
    private final ConnectionManager wifiManager;
    private final CountDownLatch wifiJoinLatch = new CountDownLatch(1);
    private volatile boolean sessionReady = false;

    public HybridConnectionManager(Context context) {
        BluetoothTransport btTransport   = new BluetoothTransport(context);
        SocketTransport    wifiTransport = new SocketTransport();

        // Inject wifiJoinCallback into wifiManager's control dispatcher
        this.wifiManager = new ConnectionManager(wifiTransport,
            /* wifiJoinCallback */ wifiJoinLatch::countDown);

        this.btManager = new ConnectionManager(btTransport);
    }

    // Call after CompanionDeviceManager returns the device address (first launch)
    // or after reading saved address from SharedPreferences (subsequent launches)
    public CompletableFuture<Void> connect(String btDeviceAddress) {
        return CompletableFuture.runAsync(() -> {
            try {
                // 1. Connect BT transport and run BT session handshake
                btManager.connectTransport(btDeviceAddress);
                SessionInfo info = btManager.joinBtSession(); // client sends MagicBytes, receives SESSION_INFO

                // 2. Connect Wi-Fi using address from SESSION_INFO
                wifiManager.connectTransportToAddress(info.wifiHost, info.wifiPort);

                // 3. Send SESSION_JOIN, wait for ACK
                wifiManager.joinSession(ConnectionContext.getInstance().getSessionToken());

                // 4. Wait for server-side Wi-Fi join confirmation (wifiJoinCallback fires on server)
                // On client side, joinSession() already confirmed ACK received — sessionReady here
                sessionReady = true;
            } catch (Exception e) {
                throw new RuntimeException("Hybrid connect failed", e);
            }
        });
    }

    public ConnectionManager getEcoManager()         { assertReady(); return btManager; }
    public ConnectionManager getPerformanceManager() { assertReady(); return wifiManager; }

    private void assertReady() {
        if (!sessionReady) throw new IllegalStateException("Session not established yet");
    }
}
```

**Windows — `HybridConnectionManager.cs` (server side):**

```csharp
public class HybridConnectionManager
{
    private readonly ConnectionManager _btManager;
    private readonly ConnectionManager _wifiManager;
    private readonly TaskCompletionSource _wifiJoinTcs = new TaskCompletionSource();

    public HybridConnectionManager()
    {
        // Inject wifiJoinCallback — fires when SESSION_JOIN is verified on the Wi-Fi manager
        _wifiManager = new ConnectionManager(new SocketTransport(),
            wifiJoinCallback: () => _wifiJoinTcs.TrySetResult());

        _btManager = new ConnectionManager(new BluetoothTransport());
    }

    public async Task StartAsync()
    {
        // Start both listeners in parallel — either can receive a connection first
        var btListenTask   = _btManager.StartTransportListeningAsync();
        var wifiListenTask = _wifiManager.StartTransportListeningAsync();
        await Task.WhenAll(btListenTask, wifiListenTask);

        // Run BT session handshake (sends SESSION_INFO to Android)
        await _btManager.StartBtSessionAsync();

        // Wait for Android to connect Wi-Fi and send SESSION_JOIN
        using var cts = new CancellationTokenSource(
            TimeSpan.FromMilliseconds(CoreConfig.SessionJoinAckTimeoutMs));
        await _wifiJoinTcs.Task.WaitAsync(cts.Token);
        // If timeout: throw, surface error to caller
    }

    public ConnectionManager EcoManager         => _btManager;
    public ConnectionManager PerformanceManager => _wifiManager;
}
```

**Test after Phase 4:** Full end-to-end Hybrid flow — BT session handshake, Wi-Fi join, both managers available. Open a channel on `EcoManager` and exchange data. Open a channel on `PerformanceManager` and exchange data. Both simultaneously — verify no cross-talk.

---

### Phase 5 — BLE Discovery

This phase handles the first-time pairing UX. After the first pairing, the saved device address is used directly and BLE is only used again if the bond is lost.

**Windows — `BleAdvertiser.cs`:**

```csharp
public class BleAdvertiser
{
    private GattServiceProvider? _serviceProvider;

    public async Task StartAsync()
    {
        // Check hardware capability first
        var btAdapter = await BluetoothAdapter.GetDefaultAsync();
        if (btAdapter == null || !btAdapter.IsPeripheralRoleSupported)
            return; // BLE peripheral not supported — skip advertising, manual MAC entry required

        var result = await GattServiceProvider.CreateAsync(CoreConfig.BleServiceUuid);
        if (result.Error != BluetoothError.Success)
            throw new InvalidOperationException($"GATT create failed: {result.Error}");

        _serviceProvider = result.ServiceProvider;

        _serviceProvider.StartAdvertising(new GattServiceProviderAdvertisingParameters
        {
            IsDiscoverable = true,
            IsConnectable  = false // BLE is discovery-only; data travels on RFCOMM Classic
        });
    }

    public void Stop() => _serviceProvider?.StopAdvertising();
}
```

`IsConnectable = false`: Android does not need to connect to the GATT service — the mere presence of `BLE_SERVICE_UUID` in the advertisement is the signal. No GATT characteristics need to be defined.

**Android — `BleDiscovery.java`:**

```java
public class BleDiscovery {

    public interface PairingCallback {
        void onDevicePaired(BluetoothDevice device);
        void onPairingFailed(String reason);
    }

    public void startDiscovery(Activity activity, PairingCallback callback) {
        // BluetoothLeDeviceFilter — matches BLE advertisements carrying BLE_SERVICE_UUID.
        // This is the correct filter type because Windows advertises via BLE, not Classic.
        // Using BluetoothDeviceFilter (Classic) here would find every nearby BT device — wrong.
        BluetoothLeDeviceFilter filter = new BluetoothLeDeviceFilter.Builder()
            .setScanFilter(new ScanFilter.Builder()
                .setServiceUuid(ParcelUuid.fromString(CoreConfig.BLE_SERVICE_UUID))
                .build())
            .build();

        AssociationRequest request = new AssociationRequest.Builder()
            .addDeviceFilter(filter)
            .setSingleDevice(false)
            .build();

        CompanionDeviceManager manager =
            (CompanionDeviceManager) activity.getSystemService(Context.COMPANION_DEVICE_SERVICE);

        manager.associate(request, new CompanionDeviceManager.Callback() {
            @Override
            public void onDeviceFound(IntentSender chooserLauncher) {
                // OS shows native "Found nearby device" popup — no custom UI needed
                // Note: startIntentSenderForResult is deprecated in API 33+.
                // Use ActivityResultLauncher / registerForActivityResult for new code targeting API 33+.
                try {
                    activity.startIntentSenderForResult(
                        chooserLauncher, REQUEST_CODE_PAIRING, null, 0, 0, 0);
                } catch (IntentSender.SendIntentException e) {
                    callback.onPairingFailed(e.getMessage());
                }
            }
            @Override
            public void onFailure(CharSequence error) {
                callback.onPairingFailed(error.toString());
            }
        }, null);
    }

    // Call from onActivityResult
    public void onActivityResult(int requestCode, int resultCode,
                                  Intent data, PairingCallback callback) {
        if (requestCode != REQUEST_CODE_PAIRING) return;
        if (resultCode != Activity.RESULT_OK) {
            callback.onPairingFailed("user cancelled");
            return;
        }
        BluetoothDevice device = data.getParcelableExtra(CompanionDeviceManager.EXTRA_DEVICE);
        if (device != null) callback.onDevicePaired(device);
        else                callback.onPairingFailed("no device in result");
    }

    private static final int REQUEST_CODE_PAIRING = 1001;
}
```

After `onDevicePaired`, the caller:
1. Saves `device.getAddress()` to SharedPreferences under key `"tausync_bt_device_address"`.
2. Passes the address to `HybridConnectionManager.connect(address)`.

On subsequent launches, read the address from SharedPreferences and call `HybridConnectionManager.connect(address)` directly — `BleDiscovery` is skipped. `BluetoothTransport.connect()` will check bond state and call `BleDiscovery.startDiscovery()` automatically if the bond was lost (see Phase 1 connect code).

**AndroidManifest.xml additions:**
```xml
<uses-permission android:name="android.permission.BLUETOOTH" />
<uses-permission android:name="android.permission.BLUETOOTH_ADMIN" />
<!-- API 31+ — these are runtime permissions; request them before calling BleDiscovery or BluetoothTransport -->
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
<uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
<uses-permission android:name="android.permission.BLUETOOTH_ADVERTISE" />
<!-- Mark BT as optional so the app still installs on devices without BT hardware -->
<uses-feature android:name="android.hardware.bluetooth" android:required="false" />
<uses-feature android:name="android.hardware.bluetooth_le" android:required="false" />
```

For API 31+, request `BLUETOOTH_CONNECT` and `BLUETOOTH_SCAN` via `ActivityCompat.requestPermissions` before calling any BT code. Gate the entire Hybrid flow behind a BT availability check:
```java
BluetoothAdapter adapter = ((BluetoothManager)
    context.getSystemService(Context.BLUETOOTH_SERVICE)).getAdapter();
if (adapter == null || !adapter.isEnabled()) {
    // BT unavailable — fall back to Wi-Fi only flow
}
```

---

### Phase 6 — SDK Integration

**Android — `TauSync.java`:**

```java
public class TauSync {
    // All existing methods unchanged

    // New factory methods
    public HybridConnectionManager newHybridManager(Context context) {
        return new HybridConnectionManager(context);
    }

    // Eco = BT only. Caller is responsible for connecting BluetoothTransport first.
    public ConnectionManager newEcoManager(Context context) {
        return new ConnectionManager(new BluetoothTransport(context));
    }

    // Performance = Wi-Fi only. Identical to existing newManager().
    public ConnectionManager newPerformanceManager() {
        return new ConnectionManager(new SocketTransport());
    }
}
```

**Windows SDK:** Same three factory methods, same logic.

---

## 7. Fallback Path — No Changes Required

When the app uses `newPerformanceManager()` (or the existing `newManager()` — they are identical), it creates a `ConnectionManager` with `SocketTransport`. This is the current Wi-Fi-only flow. The new SESSION_JOIN branch in the control dispatcher is only reached when `Type == "SESSION_JOIN"` — existing handshake messages have no `Type` field and fall through to the existing handler untouched.

---

## 8. Platform-Specific API Reference

### Windows — Key namespaces

```
Windows.Devices.Bluetooth                              → BluetoothAdapter (capability check)
Windows.Devices.Bluetooth.Advertisement               → (not used — BleAdvertiser uses GATT)
Windows.Devices.Bluetooth.GenericAttributeProfile     → GattServiceProvider, GattServiceProviderAdvertisingParameters
Windows.Devices.Bluetooth.Rfcomm                      → RfcommServiceProvider, RfcommServiceId
Windows.Networking.Sockets                            → StreamSocketListener, StreamSocket (RFCOMM uses these, same as TCP)
```

NuGet: No extra packages needed for WinRT apps. For .NET without WinRT projection, add `Microsoft.Windows.SDK.Contracts`.

### Android — Key classes

```
android.bluetooth.BluetoothManager           → getAdapter() (API 31+ preferred over getDefaultAdapter)
android.bluetooth.BluetoothAdapter           → cancelDiscovery(), getRemoteDevice()
android.bluetooth.BluetoothDevice            → createRfcommSocketToServiceRecord(), getBondState()
android.bluetooth.BluetoothSocket            → connect(), getInputStream(), getOutputStream()
android.companion.CompanionDeviceManager     → associate() — triggers native OS pairing popup (API 26+)
android.companion.AssociationRequest         → filter config
android.companion.BluetoothLeDeviceFilter    → filter by BLE_SERVICE_UUID (use this, not BluetoothDeviceFilter)
android.bluetooth.le.ScanFilter              → setServiceUuid() used inside BluetoothLeDeviceFilter
```

Min API for `CompanionDeviceManager`: 26. Min API for runtime BT permissions: 31. RFCOMM itself works from API 18+. If `minSdk < 26`, gate `BleDiscovery` behind a version check and fall back to manual MAC entry.

---

## 9. Testing Checklist

Work through these in order. Each item assumes the previous ones pass.

- [ ] `BluetoothTransport` server+client connect, exchange a raw byte array, disconnect cleanly
- [ ] `BluetoothTransport` receive loop correctly parses TPack frames (run existing `ProtocolHandler` unit tests piped through BT streams)
- [ ] `SocketTransport.disconnect()` calls `NotifyTransportDisconnected()` and does NOT call `reset()` directly (verify in code)
- [ ] `ConnectionContext.sessionToken` set, retrieved, and cleared by `reset()`
- [ ] `ConnectionContext.notifyTransportConnected/Disconnected()` — connect two transports, disconnect one, verify `reset()` is NOT called; disconnect second, verify `reset()` IS called
- [ ] BT_MAGIC exchanged on both sides, mismatch case closes connection cleanly
- [ ] `startBtSession()` — SERVER generates token, sends SESSION_INFO, token stored in ConnectionContext
- [ ] `joinBtSession()` — CLIENT receives SESSION_INFO, stores token, returns correct WifiHost/WifiPort
- [ ] Wi-Fi TCP connect → SESSION_JOIN sent → SERVER verifies token → SESSION_JOIN_ACK received
- [ ] Invalid token on SESSION_JOIN → server closes TCP immediately, no crash, no state corruption
- [ ] SESSION_JOIN_ACK timeout → `joinSession()` throws, caller can handle gracefully
- [ ] `HybridConnectionManager.connect()` runs the full flow end-to-end on real hardware
- [ ] Channel opened on `EcoManager` (BT) sends and receives data
- [ ] Channel opened on `PerformanceManager` (Wi-Fi) sends and receives data
- [ ] Both channels open simultaneously — no cross-talk between them
- [ ] BT disconnects mid-session — Wi-Fi channels remain alive, BT channels return EOF, `reset()` not called yet
- [ ] Wi-Fi disconnects mid-session — BT channels remain alive, Wi-Fi channels return EOF, `reset()` not called yet
- [ ] Both transports disconnect — `reset()` called exactly once
- [ ] `BleAdvertiser` — Windows advertises, Android `CompanionDeviceManager` shows native popup with only TauSync PC (not all nearby devices)
- [ ] Saved device address reused on second app launch — BLE popup does NOT appear
- [ ] Bond lost (unpairing from system settings) — `BluetoothTransport.connect()` detects it, triggers `BleDiscovery` automatically, RFCOMM connects after re-pairing
- [ ] BLE peripheral not supported on Windows hardware — `BleAdvertiser.StartAsync()` exits gracefully, falls back to manual MAC
- [ ] Existing Wi-Fi-only flow (`newManager()` + manual IP) completely unaffected by all above changes

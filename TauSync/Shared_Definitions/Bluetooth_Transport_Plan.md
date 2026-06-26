# TauSync — Bluetooth Transport

## Motivation

TauSync currently runs exclusively over TCP/Wi-Fi. This means both devices must share the same network — the same router, the same subnet, and no firewall blocking peer-to-peer traffic. In practice this is a significant constraint: corporate networks, hotel Wi-Fi, captive portals, and mobile hotspots regularly prevent device-to-device TCP connections. TauSync silently fails in all of these environments.

Adding Bluetooth Classic (RFCOMM) as a second transport layer solves this at the root. Bluetooth is a direct physical link between devices — no router, no NAT traversal, no firewall. Once two devices are paired, they can establish a TauSync session regardless of what network they are (or are not) on.

### Why Bluetooth Classic and not BLE

Bluetooth Low Energy is designed for small, infrequent payloads (sensor readings, beacons). Its MTU cap (~512 bytes) and connection-oriented GATT model are fundamentally mismatched with TauSync's streaming multiplexed protocol. Bluetooth Classic RFCOMM provides a full-duplex byte stream — the same abstraction as a TCP socket — which means the entire TauSync protocol stack above the transport layer requires no changes.

### Why this fits the existing architecture

`ITransport` (C#) and the transport interface (Android) were already designed as transport-agnostic interfaces. `SocketTransport` is one implementation; `BluetoothTransport` is another. The protocol, multiplexing, and SDK layers are completely unaware of what carries the bytes. This is a Layer 1 addition, not a protocol change.

### What it unlocks

- **Connectivity independence** — sync works anywhere two devices are within ~10 meters, regardless of network.
- **Simpler connection UX** — Bluetooth pairing replaces manual IP entry. After the first pair, reconnection is automatic.
- **Automatic performance scaling** — the same `ConnectionManager` sends small frames over BT and large frames over Wi-Fi, connecting Wi-Fi only when it's actually needed.

### Accepted tradeoff

Bluetooth Classic throughput is roughly 1–3 Mbps effective, compared to tens or hundreds of Mbps over Wi-Fi. Large file transfers will be noticeably slower over BT. This is acceptable: the Bluetooth transport is the "always works" path, not the "maximum performance" path. Wi-Fi is added lazily when large payloads need it.

---

## Implementation Plan

---

## 1. High-Level Architecture

After this feature is complete, a TauSync session can run over three configurations:

| Mode | Transport | When used |
|------|-----------|-----------|
| Wi-Fi only (existing) | `SocketTransport` | No Bluetooth available, or user has not paired |
| Bluetooth only | `BluetoothTransport` | No shared Wi-Fi network |
| Hybrid | `BluetoothTransport` primary + `SocketTransport` lazy | Both available — BT is always connected; Wi-Fi connects on demand for large payloads |

The protocol stack does not change. `BluetoothTransport` is a `ITransport` implementation alongside `SocketTransport`. Everything at Layer 2 and above is unaffected.

**There is no separate `HybridConnectionManager`, `EcoConnectionManager`, or `PerformanceConnectionManager` class.** `ConnectionManager` itself accepts one or two transports and handles routing internally. The caller does not choose transports per-channel — the manager auto-routes based on payload size.

- **Single-transport mode** (`new ConnectionManager(socketTransport)` or `new ConnectionManager(btTransport)`) — behaves exactly as today, no routing logic.
- **Hybrid mode** (`new ConnectionManager(btTransport, socketTransport)`) — BT is the primary transport, always connected. Wi-Fi is lazy: it connects on demand when a payload exceeds `HYBRID_SMALL_THRESHOLD_BYTES`, coordinated via a request/ready protocol over BT, and disconnects after 60 seconds of idle.

Wi-Fi-only mode (existing behavior, single `SocketTransport`) is completely unchanged.

---

## 2. Full Connection Flow

### 2.1 Happy Path (Hybrid — BT + Wi-Fi)

```
Windows (server)                             Android (client)
────────────────                             ────────────────
ConnectionManager(btTransport, wifiTransport):
  BluetoothTransport.Connect(null)
    └─ RFCOMM listener waiting

                                             First launch — BleDiscovery.startDiscovery()
                                             ← BLE advertisement found (BluetoothLeDeviceFilter
                                               matching BLE_SERVICE_UUID)
                                             OS shows native pairing popup
                                             User taps "Connect"
                                             device.getAddress() saved to SharedPreferences
                                             (future launches skip BleDiscovery entirely)

                          ←── RFCOMM socket opens ───────────

BT Session Handshake (TargetID=0, no meeting word):
  Server → Client: {"MagicBytes": 1414743891}
  Client → Server: {"MagicBytes": 1414743891}
  Both sides confirm peer is a valid TauSync endpoint.
  Server generates sessionToken, stores in ConnectionContext.

Both sides now connected over BT only.
Small frames (<= 64 KB) flow over BT.

── Later: first large payload (> 64 KB) on either side ──────────────────────

Side that needs Wi-Fi sends over BT:          Side that needs Wi-Fi sends over BT:
WIFI_CONNECT_REQ ───────────────────────────→
                                             (Windows is always Wi-Fi server)
                                             Starts TCP listener
                              ←──────────────  WIFI_CONNECT_READY
                                               {"Type":"WIFI_CONNECT_READY",
                                                "SessionToken":"<token>",
                                                "WifiHost":"192.168.x.x",
                                                "WifiPort":5000}
Opens TCP to WifiHost:WifiPort ─────────────→
Sends SESSION_JOIN on TCP ───────────────────→
  {"MagicBytes":1414743891,
   "Type":"SESSION_JOIN",
   "SessionToken":"<token>"}
                                             Verifies token == ConnectionContext.getSessionToken()
                              ←──────────────  SESSION_JOIN_ACK
                                               {"Type":"SESSION_JOIN_ACK"}

Wi-Fi is now live. Large payload sent over Wi-Fi.
60-second idle timer starts on both sides.
If no frame received on Wi-Fi for 60s → both sides disconnect Wi-Fi cleanly.
Next large payload triggers WIFI_CONNECT_REQ again from scratch.
```

### 2.2 Returning Launch (Device Already Paired)

Identical to 2.1 except BleDiscovery is skipped entirely. Android reads the saved device address from SharedPreferences and calls `BluetoothTransport.connect(savedAddress)` directly.

### 2.3 Bond Lost (Device Unpaired from System Settings)

`BluetoothTransport.connect()` checks `device.getBondState() == BOND_BONDED` before attempting RFCOMM. If the bond is gone, it triggers `BleDiscovery.startDiscovery()` automatically to re-pair, then retries the RFCOMM connect after the new bond is established. The saved address in SharedPreferences is updated with the result.

### 2.4 Fallback Path (Wi-Fi Only — No Changes)

If Bluetooth is unavailable or the user never paired, the app creates `ConnectionManager` with a single `SocketTransport`. No routing, no BT handshake, no `WIFI_CONNECT_REQ` protocol. Behaves exactly as today.

### 2.5 Transport Drop Fallback (Hybrid Mode)

| Situation | Behavior |
|-----------|----------|
| BT drops unexpectedly | Phase 2 reconnect loop fires for BT. All frames (including small ones) reroute to Wi-Fi if it is connected. |
| Wi-Fi drops unexpectedly | Phase 2 reconnect loop fires for Wi-Fi. All frames reroute to BT (degraded throughput). |
| Both drop | Sends block on Phase 2 send gate. Session stays alive waiting for either to reconnect. |
| Explicit `disconnect()` on all transports | `activeTransportCount` hits 0 → `abortAllChannels()` + `reset()`. |

---

## 3. Routing Algorithm

Applied per outgoing frame inside `ConnectionManager.sendRaw()` / `SendRaw()`:

```
if only one transport configured:
    send on it  ← single-transport mode, no routing

else (hybrid mode):
    if payload.length <= HYBRID_SMALL_THRESHOLD_BYTES:
        send on BT

    else (large payload):
        if Wi-Fi is connected:
            send on Wi-Fi
            reset 60s idle timer
        else:
            trigger WIFI_CONNECT_REQ flow (see Section 2.1)
            wait on wifiSendGate (blocks until Wi-Fi is up)
            send on Wi-Fi
```

Incoming frames: both receive loops run independently and share the same `targetId → handler` routing map in `ConnectionContext`. A frame arriving on either transport dispatches correctly regardless of which transport carried it.

**Wi-Fi idle disconnect:** Both sides track last-received-frame time on the Wi-Fi transport. When 60 seconds pass without any received frame, call `disconnect()` on `SocketTransport` (intentional close — Phase 2 reconnect loop does NOT fire). `activeTransportCount` does not hit 0 because BT is still up, so channels are not aborted. The next large payload triggers `WIFI_CONNECT_REQ` again.

**Role assignment:** BT server (Windows) = Wi-Fi TCP server (starts listener, sends `WIFI_CONNECT_READY`). BT client (Android) = Wi-Fi TCP client (connects, sends `SESSION_JOIN`). Fixed for the session lifetime.

---

## 4. Protocol Changes

### 4.1 New CoreConfig Constants

Already added in Phase 1. Listed here for reference — all values must match across platforms.

```java
// Android — CoreConfig.java
public static final String BLE_SERVICE_UUID             = "12345678-1234-5678-1234-56789abcde01";
public static final String RFCOMM_SERVICE_UUID          = "12345678-1234-5678-1234-56789abcde02";
public static final int    BT_CONNECT_TIMEOUT_MS        = 15_000;
public static final int    SESSION_JOIN_ACK_TIMEOUT_MS  = 10_000;
public static final int    HYBRID_SMALL_THRESHOLD_BYTES = 65_536; // 64 KB
public static final int    WIFI_IDLE_TIMEOUT_MS         = 60_000; // 60 s
public static final int    RECONNECT_INITIAL_DELAY_MS   = 1_000;
public static final int    RECONNECT_MAX_DELAY_MS       = 30_000;
public static final int    SEND_RECONNECT_WAIT_MS       = 30_000;
```

```csharp
// Windows — Core.cs
public static readonly Guid BleServiceUuid             = new Guid("12345678-1234-5678-1234-56789abcde01");
public static readonly Guid RfcommServiceUuid          = new Guid("12345678-1234-5678-1234-56789abcde02");
public const int BtConnectTimeoutMs                    = 15_000;
public const int SessionJoinAckTimeoutMs               = 10_000;
public const int HybridSmallThresholdBytes             = 65_536; // 64 KB
public const int WifiIdleTimeoutMs                     = 60_000; // 60 s
public const int ReconnectInitialDelayMs               = 1_000;
public const int ReconnectMaxDelayMs                   = 30_000;
public const int SendReconnectWaitMs                   = 30_000;
```

`HYBRID_SMALL_THRESHOLD_BYTES` is a constant so it can be tuned without touching logic. `ConnectionManager` reads it to decide routing — it is never hardcoded.

`WIFI_IDLE_TIMEOUT_MS` needs to be added in Phase 3.

### 4.2 Control Channel Message Types

All sent on TargetID = 0 with `FLAG_CONTROL`. Existing handshake messages have no `Type` field and are unaffected by the new branches.

**BT_MAGIC** — exchanged on both sides immediately after RFCOMM opens. Confirms both peers are TauSync endpoints. No meeting word.
```json
{"MagicBytes": 1414743891}
```

**WIFI_CONNECT_REQ** — sent by either side over BT when it first needs Wi-Fi (large payload queued).
```json
{"Type": "WIFI_CONNECT_REQ"}
```

**WIFI_CONNECT_READY** — sent by the Wi-Fi server (BT server = Wi-Fi server always) over BT in reply. Carries the session token and TCP address.
```json
{
  "Type": "WIFI_CONNECT_READY",
  "SessionToken": "<uuid-v4>",
  "WifiHost": "192.168.1.100",
  "WifiPort": 5000
}
```

**SESSION_JOIN** — sent by the Wi-Fi client as the very first frame on the new TCP socket.
```json
{
  "MagicBytes": 1414743891,
  "Type": "SESSION_JOIN",
  "SessionToken": "<uuid-v4>"
}
```
`MagicBytes` is included so the server's existing control-channel dispatcher recognizes the frame as valid before branching on `Type`.

**SESSION_JOIN_ACK** — sent by the Wi-Fi server after successful token verification.
```json
{"Type": "SESSION_JOIN_ACK"}
```

If the token does not match, the server closes the TCP connection immediately with no response.

### 4.3 Session Token Lifecycle

- Generated server-side (Windows) immediately after BT_MAGIC exchange succeeds: `UUID.randomUUID().toString()` / `Guid.NewGuid().ToString()`.
- Stored in `ConnectionContext.sessionToken` (nullable string, initially null).
- Sent to the client inside `WIFI_CONNECT_READY` when Wi-Fi is first requested.
- Client stores the token in `ConnectionContext.setSessionToken()` on receiving `WIFI_CONNECT_READY`.
- Used once to verify `SESSION_JOIN`. After that it remains stored but is not reused.
- Cleared by `ConnectionContext.reset()` (which fires only when the last transport explicitly disconnects).

### 4.4 Existing Handshake is Untouched

The regular `ConnectionManager` meeting-word handshake (used for app-level channels) is unchanged. The new control message types are dispatched by checking the `"Type"` field; existing handshake messages have no `Type` field and fall through to the existing handler untouched.

---

## 5. Files to Create

### Windows (C#)

| File | Purpose |
|------|---------|
| `TauSync.Lib/Implementations/Discovery/BleAdvertiser.cs` | BLE GATT peripheral, advertises TauSync `BLE_SERVICE_UUID` for first-time pairing (Phase 4) |

### Android (Java)

| File | Purpose |
|------|---------|
| `tausync-lib/implementations/discovery/BleDiscovery.java` | `CompanionDeviceManager` + bond-loss re-pairing (Phase 4) |

`BluetoothTransport.cs` and `BluetoothTransport.java` were created in Phase 1 and are complete.

---

## 6. Files to Modify

| File | Change | Phase |
|------|--------|-------|
| `CoreConfig.java` / `Core.cs` | Add `WIFI_IDLE_TIMEOUT_MS` | 3 |
| `ConnectionContext.java` / `ConnectionContext.cs` | Add `sessionToken` field + getter/setter; clear in `reset()` | 3 |
| `ConnectionManager.java` / `ConnectionManager.cs` | Add second transport slot; routing algorithm; BT_MAGIC handshake; `WIFI_CONNECT_REQ/READY` flow; `SESSION_JOIN` dispatcher branch; 60s idle timer | 3 |
| `AndroidManifest.xml` | Add `BLUETOOTH_ADVERTISE` permission (needed for BLE advertising in Phase 4) | 4 |
| `TauSync.java` (SDK) | Expose factory methods for hybrid and single-transport managers | 5 |

---

## 7. Detailed Implementation Guide

Implement in this exact order. Each phase is independently testable before moving to the next.

---

### Phase 1 — `BluetoothTransport` (both platforms) ✅ COMPLETE

**What was done:**
- `ITransport`: added `TransportKind` enum (`WiFi/Bluetooth`, `WIFI/BLUETOOTH`) + `TransportType`/`getTransportType()`. `SocketTransport` returns `WiFi`.
- `CoreConfig`/`Core.cs`: added `BleServiceUuid`, `RfcommServiceUuid`, `BtConnectTimeoutMs`, `SessionJoinAckTimeoutMs`, `HybridSmallThresholdBytes`.
- Windows csproj TFM bumped `net8.0` → `net8.0-windows10.0.19041.0`.
- `BluetoothTransport.cs` — Windows RFCOMM server (advertises via `RfcommServiceProvider`, reads/writes via `DataReader`/`DataWriter`).
- `BluetoothTransport.java` — Android RFCOMM client (connects to paired Windows device by MAC, `createRfcommSocketToServiceRecord`).
- `AndroidManifest.xml`: added `BLUETOOTH_CONNECT`, `BLUETOOTH_SCAN`, legacy `BLUETOOTH`/`BLUETOOTH_ADMIN`.
- Hardware test passed: Windows received "hello from android" over RFCOMM.

---

### Phase 2 — Reconnect Resilience ✅ COMPLETE

**What was done (scope differs from original plan doc — see decisions below):**

- `sessionToken` was NOT added in this phase — deferred to Phase 3.
- Session ends ONLY on explicit `disconnect()`. Any unexpected drop (peer vanished, socket killed) triggers indefinite reconnect with exponential back-off (`RECONNECT_INITIAL_DELAY_MS=1s` → `RECONNECT_MAX_DELAY_MS=30s`), never `reset()`/`abortAllChannels()`.
- Channels survive drops. `routingMap`/`targetMap` and in-memory `BackBuffered*` streams stay intact so both sides resume on the same channel/stream objects with no meeting-word re-handshake after reconnect.
- `abortAllChannels()` + `reset()` fire only when the LAST transport is explicitly disconnected (ref-counted).
- `ConnectionContext` (both): `activeTransportCount` + `notifyTransportConnected()`/`notifyTransportDisconnected()`.
- `SocketTransport` + `BluetoothTransport` (both platforms): `intentionalClose` flag, `sendGate` (`TaskCompletionSource`/`CompletableFuture`), `markInitialConnection()`, `handleConnectionDropped()`, reconnect loop, `WaitForConnectionAsync()`.
- `CoreConfig`/`Core.cs`: added `RECONNECT_INITIAL_DELAY_MS`, `RECONNECT_MAX_DELAY_MS`, `SEND_RECONNECT_WAIT_MS`.
- Automated localhost WiFi reconnect test (`SocketReconnect.ManualTest`) — all 6 checks passed.

---

### Phase 3 — BT Session Handshake + Hybrid Wi-Fi Lazy Connect ✅ IMPLEMENTED (2026-06-18)

This phase upgrades `ConnectionManager` to own two transports and handle routing. After this phase, BT and Wi-Fi are a unified session from the app's perspective.

**Status:** both platforms compile; in-process C# test (`Phase3.ManualTest`, 12 checks) passes. The full two-endpoint lazy-Wi-Fi flow (REQ→READY→JOIN→ACK, idle teardown, drop fallback) is NOT run end-to-end yet — it needs two processes/machines because `ConnectionContext` is a process-wide singleton (same constraint as the real BT hardware test).

**What was built:**
- `sessionToken` + `WIFI_IDLE_TIMEOUT_MS` (Step 3a).
- `SessionControlMessage` model + a session-control dispatch hook in `ConnectionContext` (checked before meeting-word discovery; keyed by reserved `Type`).
- `NetworkUtils.getLocalWifiIpAddress()` on both platforms.
- `HybridSessionCoordinator` (owned by `ConnectionManager`) implementing the BT_MAGIC handshake, `WIFI_CONNECT_REQ/READY` + `SESSION_JOIN/_ACK` flow, size-based routing, and the 60 s idle teardown.
- `ConnectionManager(primary, secondary)` constructor; field `wifiTransport` renamed `primaryTransport`; control + small data over BT, large data routed to Wi-Fi.
- Transport additions: `ITransport.IsServerMode` (C#, to match Java) implemented on `BluetoothTransport`; `LastActivityTicks`/`getLastActivityMillis()` on `SocketTransport` for idle detection.

**Refinement vs. this doc:** BT_MAGIC carries an explicit `"Type":"BT_MAGIC"` (the doc showed a bare `{"MagicBytes":…}`) so every session-control frame dispatches uniformly by `Type`.

---

#### Phase 3 addendum (2026-06-18) — Wi-Fi IP auto-discovery over Bluetooth

Two follow-up changes so the user never types a Wi-Fi IP:

1. **BT_MAGIC carries the sender's Wi-Fi IP.** When each side sends BT_MAGIC it now fills `WifiHost`
   (from `NetworkUtils.getLocalWifiIpAddress()`) and `WifiPort` (`DEFAULT_PORT`). On receiving the
   peer's BT_MAGIC, the coordinator stores `message.WifiHost` via
   `ConnectionContext.SetPeerWifiHost()`. So the peer's Wi-Fi address is known the moment the BT
   handshake completes — earlier than `WIFI_CONNECT_READY`, which only arrives on the first large
   payload. `_peerWifiHost` is cleared by `Reset()`.
2. **The SDK exposes it and the test app auto-fills the IP field.** `ConnectionContext` gains
   `Set/GetPeerWifiHost`; the SDK exposes `getPeerWifiIp()` (Android `TauSync`) / `peer_wifi_ip`
   (Python). The Android test activity, right after `connectHybrid()` returns, writes the discovered
   IP into its `ipAddressInput` field — no manual entry for either the hybrid or the Wi-Fi-only flow.

Supporting SDK surface added for the hybrid end-to-end test harness:
- Android `TauSync`: `connectHybrid(Context, btMac)`, `getPeerWifiIp()`, `isWifiActive()`.
- Python `TauSync`: `connect_hybrid()`, `peer_wifi_ip`, `wifi_active` (Windows = BT/Wi-Fi server).

---

**Step 3a — Add `sessionToken` to `ConnectionContext` (both platforms)**

```java
// Java
private volatile String sessionToken = null;
public void setSessionToken(String token) { this.sessionToken = token; }
public String getSessionToken()           { return sessionToken; }
// In reset(): sessionToken = null;
```

```csharp
// C#
private volatile string? _sessionToken;
public void SetSessionToken(string token) => _sessionToken = token;
public string? GetSessionToken()          => _sessionToken;
// In Reset(): _sessionToken = null;
```

Also add `WIFI_IDLE_TIMEOUT_MS = 60_000` to `CoreConfig`/`Core.cs`.

---

**Step 3b — `ConnectionManager` constructor change (both platforms)**

Currently parameterless. New signatures:

```java
// Java — single transport (backward compat: Wi-Fi only or BT only)
new ConnectionManager(ITransport transport)

// Java — hybrid: BT primary + Wi-Fi lazy secondary
new ConnectionManager(ITransport primaryTransport, ITransport secondaryTransport)
```

```csharp
// C#
new ConnectionManager(ITransport transport)
new ConnectionManager(ITransport primaryTransport, ITransport secondaryTransport)
```

`getTransportType()` (added Phase 1) tells the manager which slot each transport fills. In single-transport mode all routing and handshake logic is skipped entirely.

---

**Step 3c — BT Session Handshake on connect**

Runs automatically after BT connects, before any app-level traffic. Implemented inside `ConnectionManager` when in hybrid mode.

**Server (Windows) — `startBtSession()`:**
1. Send `{"MagicBytes": 1414743891}` on TargetID=0 (`FLAG_CONTROL`).
2. Wait for peer's MagicBytes reply (timeout: `BT_CONNECT_TIMEOUT_MS`). Mismatch → close BT, throw.
3. Generate `sessionToken = Guid.NewGuid().ToString()`.
4. Store via `ConnectionContext.SetSessionToken(token)`.

**Client (Android) — `joinBtSession()`:**
1. Send `{"MagicBytes": 1414743891}` on TargetID=0.
2. Wait for peer's MagicBytes reply. Mismatch → close BT, throw.
3. *(sessionToken not yet known — received later in `WIFI_CONNECT_READY`)*

`waitForControlMessage(timeoutMs)`: a `CompletableFuture` / `TaskCompletionSource` that the control channel dispatcher resolves when a TargetID=0 frame arrives outside of an active meeting-word handshake. Analogous to the existing pending-response pattern.

---

**Step 3d — Wi-Fi Lazy Connect: `WIFI_CONNECT_REQ` / `WIFI_CONNECT_READY`**

Either side sends `WIFI_CONNECT_REQ` over BT when it first needs Wi-Fi (large payload queued and Wi-Fi not yet up):

```
Initiator (either side)                      Responder (other side)
───────────────────────                      ──────────────────────
large payload arrives, Wi-Fi not up
wifiSendGate blocks
send WIFI_CONNECT_REQ over BT ─────────────→

                                             if I am BT server (= Wi-Fi server):
                                               start TCP listener on DEFAULT_PORT
                                               find local Wi-Fi IP (NetworkUtils)
                                               store + send WIFI_CONNECT_READY over BT
                             ←───────────────
if I am BT client (= Wi-Fi client):
  store token from WIFI_CONNECT_READY
  ConnectionContext.setSessionToken(token)
  open TCP to WifiHost:WifiPort ────────────→
  send SESSION_JOIN on TCP ─────────────────→
                                             verify token == ConnectionContext.getSessionToken()
                                             if mismatch → close TCP, no ACK
                             ←───────────────  send SESSION_JOIN_ACK
wifiSendGate opens
queued large payload sent over Wi-Fi
```

If both sides simultaneously try to send a large payload, both send `WIFI_CONNECT_REQ`. The BT server receives the client's request and the client receives the server's — handle deduplication by checking: if I am the Wi-Fi server and I already started the listener, ignore a duplicate `WIFI_CONNECT_REQ`.

**`NetworkUtils.getLocalWifiIpAddress()`:** enumerate network interfaces → pick the one that is up, not loopback, not a BT interface, and has an IPv4 address. Shared utility class on both platforms. Known limitation: VPN or multi-adapter machines may pick the wrong IP — acceptable for now.

---

**Step 3e — `SESSION_JOIN` branch in the control dispatcher (server side)**

Add before the existing meeting-word logic in the control frame handler:

```java
if ("SESSION_JOIN".equals(parsed.get("Type"))) {
    String incoming = (String) parsed.get("SessionToken");
    String expected = ConnectionContext.getInstance().getSessionToken();
    if (expected == null || !expected.equals(incoming)) {
        wifiTransport.disconnect(); // invalid token — close TCP only, BT stays up
        return;
    }
    byte[] ack = gson.toJson(Map.of("Type", "SESSION_JOIN_ACK"))
                     .getBytes(StandardCharsets.UTF_8);
    wifiTransport.sendRaw(protocolHandler.buildFrame(
        CoreConfig.CONTROL_CHANNEL_ID, ack, CoreConfig.FLAG_CONTROL)).get();
    return;
}
```

Existing handshake messages have no `Type` field → fall through to existing logic untouched.

---

**Step 3f — Routing in `sendRaw` / `SendRaw`**

```
if single-transport mode:
    send on the one transport

else (hybrid mode):
    if payload.length <= CoreConfig.HYBRID_SMALL_THRESHOLD_BYTES:
        send on BT transport

    else:
        if Wi-Fi transport is connected:
            send on Wi-Fi transport
            reset wifiIdleTimer
        else:
            if Wi-Fi connect is not already in progress:
                trigger WIFI_CONNECT_REQ flow (async)
            await wifiSendGate (up to SESSION_JOIN_ACK_TIMEOUT_MS)
            send on Wi-Fi transport
```

---

**Step 3g — Wi-Fi idle timeout**

Both sides run a 60-second timer, reset on every frame received over Wi-Fi. On expiry:
- Call `wifiTransport.disconnect()` — intentional close, so Phase 2 reconnect loop does NOT fire.
- `activeTransportCount` does not hit 0 (BT still up) → channels not aborted.
- Reset `wifiSendGate` to incomplete so the next large payload triggers `WIFI_CONNECT_REQ` again.

---

**Step 3h — Test Plan**

1. BT connects → BT_MAGIC exchanged → `getSessionToken()` set on server.
2. Small payload (≤ 64 KB) → arrives over BT, Wi-Fi never triggered.
3. Large payload (> 64 KB) → `WIFI_CONNECT_REQ` over BT → `WIFI_CONNECT_READY` received → TCP connects → `SESSION_JOIN` / `SESSION_JOIN_ACK` → payload arrives over Wi-Fi.
4. Second large payload immediately → reuses existing Wi-Fi, no second handshake.
5. 60s idle → Wi-Fi disconnects cleanly, BT still alive, channels unaffected.
6. Large payload after idle → full `WIFI_CONNECT_REQ` flow again.
7. BT drops mid-session → large payload reroutes to Wi-Fi.
8. Wi-Fi drops mid-session → large payload reroutes to BT (degraded).
9. Invalid `SESSION_JOIN` token → server closes TCP, no crash, no state corruption.
10. Session join ACK timeout → `wifiSendGate` fails, caller sees exception.
11. Wi-Fi-only mode (single `SocketTransport`) → existing behavior completely unaffected.

---

### Phase 4 — BLE Discovery

This phase handles the first-time pairing UX. After the first pairing the saved device address is used directly; BLE is only used again if the bond is lost.

**Windows — `BleAdvertiser.cs`:**

```csharp
public class BleAdvertiser
{
    private GattServiceProvider? _serviceProvider;

    public async Task StartAsync()
    {
        var btAdapter = await BluetoothAdapter.GetDefaultAsync();
        if (btAdapter == null || !btAdapter.IsPeripheralRoleSupported)
            return; // BLE peripheral not supported — skip, manual MAC entry required

        var result = await GattServiceProvider.CreateAsync(CoreConfig.BleServiceUuid);
        if (result.Error != BluetoothError.Success)
            throw new InvalidOperationException($"GATT create failed: {result.Error}");

        _serviceProvider = result.ServiceProvider;
        _serviceProvider.StartAdvertising(new GattServiceProviderAdvertisingParameters
        {
            IsDiscoverable = true,
            IsConnectable  = false // discovery-only; data travels on RFCOMM Classic
        });
    }

    public void Stop() => _serviceProvider?.StopAdvertising();
}
```

`IsConnectable = false`: Android does not need to connect to the GATT service — the mere presence of `BLE_SERVICE_UUID` in the advertisement is the signal.

**Android — `BleDiscovery.java`:**

```java
public class BleDiscovery {

    public interface PairingCallback {
        void onDevicePaired(BluetoothDevice device);
        void onPairingFailed(String reason);
    }

    public void startDiscovery(Activity activity, PairingCallback callback) {
        // BluetoothLeDeviceFilter matches BLE advertisements carrying BLE_SERVICE_UUID.
        // Do NOT use BluetoothDeviceFilter (Classic) — that finds every nearby BT device.
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
                // OS shows native pairing popup — no custom UI needed.
                // startIntentSenderForResult is deprecated in API 33+;
                // use ActivityResultLauncher / registerForActivityResult for API 33+.
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

    public void onActivityResult(int requestCode, int resultCode,
                                  Intent data, PairingCallback callback) {
        if (requestCode != REQUEST_CODE_PAIRING) return;
        if (resultCode != Activity.RESULT_OK) { callback.onPairingFailed("user cancelled"); return; }
        BluetoothDevice device = data.getParcelableExtra(CompanionDeviceManager.EXTRA_DEVICE);
        if (device != null) callback.onDevicePaired(device);
        else                callback.onPairingFailed("no device in result");
    }

    private static final int REQUEST_CODE_PAIRING = 1001;
}
```

After `onDevicePaired`:
1. Save `device.getAddress()` to SharedPreferences under key `"tausync_bt_device_address"`.
2. Pass the address to `ConnectionManager` (hybrid mode) to start the BT connect.

On subsequent launches: read the address from SharedPreferences and pass directly — `BleDiscovery` is skipped. `BluetoothTransport.connect()` checks bond state and calls `BleDiscovery.startDiscovery()` automatically if the bond was lost.

**AndroidManifest.xml — add `BLUETOOTH_ADVERTISE`:**
```xml
<uses-permission android:name="android.permission.BLUETOOTH_ADVERTISE" />
<uses-feature android:name="android.hardware.bluetooth_le" android:required="false" />
```

(Other BT permissions were already added in Phase 1.)

**Test after Phase 4:**
- Windows advertises BLE; Android `CompanionDeviceManager` shows native popup with only the TauSync PC (not all nearby devices).
- Saved address reused on second launch — BLE popup does NOT appear.
- Bond lost (unpair from system settings) → `BluetoothTransport.connect()` detects it, triggers `BleDiscovery`, RFCOMM connects after re-pairing.
- BLE peripheral not supported on Windows hardware → `BleAdvertiser.StartAsync()` exits gracefully (manual MAC entry fallback).

---

### Phase 5 — SDK Integration

**Android — `TauSync.java`:**

```java
public class TauSync {
    // All existing methods unchanged.

    // Hybrid: BT primary + Wi-Fi lazy. Caller provides the paired device MAC address.
    public ConnectionManager newHybridManager(Context context, String btDeviceAddress) {
        BluetoothTransport bt   = new BluetoothTransport(context);
        SocketTransport    wifi = new SocketTransport();
        return new ConnectionManager(bt, wifi);
    }

    // BT only. Caller provides the paired device MAC address.
    public ConnectionManager newBtManager(Context context) {
        return new ConnectionManager(new BluetoothTransport(context));
    }

    // Wi-Fi only. Identical to existing newManager().
    public ConnectionManager newWifiManager() {
        return new ConnectionManager(new SocketTransport());
    }
}
```

**Windows SDK:** Same three factory methods, same logic.

---

## 8. Fallback Path — No Changes Required

`new ConnectionManager(new SocketTransport())` (or the existing `newManager()`) creates a single-transport manager. No routing, no BT handshake, no `WIFI_CONNECT_REQ` protocol. Behaves exactly as today. The new control message branches are never reached because they check for `"Type"` fields that existing handshake messages do not have.

---

## 9. Platform-Specific API Reference

### Windows — Key namespaces

```
Windows.Devices.Bluetooth                              → BluetoothAdapter (capability check)
Windows.Devices.Bluetooth.GenericAttributeProfile     → GattServiceProvider (BLE advertising)
Windows.Devices.Bluetooth.Rfcomm                      → RfcommServiceProvider, RfcommServiceId
Windows.Networking.Sockets                            → StreamSocketListener, StreamSocket
```

NuGet: No extra packages for WinRT apps. For .NET without WinRT projection, add `Microsoft.Windows.SDK.Contracts`.

### Android — Key classes

```
android.bluetooth.BluetoothManager           → getAdapter() (API 31+ preferred over getDefaultAdapter)
android.bluetooth.BluetoothAdapter           → cancelDiscovery(), getRemoteDevice()
android.bluetooth.BluetoothDevice            → createRfcommSocketToServiceRecord(), getBondState()
android.bluetooth.BluetoothSocket            → connect(), getInputStream(), getOutputStream()
android.companion.CompanionDeviceManager     → associate() — native OS pairing popup (API 26+)
android.companion.BluetoothLeDeviceFilter    → filter by BLE_SERVICE_UUID (not BluetoothDeviceFilter)
android.bluetooth.le.ScanFilter              → setServiceUuid() inside BluetoothLeDeviceFilter
```

Min API for `CompanionDeviceManager`: 26. Min API for runtime BT permissions: 31. RFCOMM works from API 18+. If `minSdk < 26`, gate `BleDiscovery` behind a version check and fall back to manual MAC entry.

---

## 10. Testing Checklist

Work through these in order. Each item assumes the previous ones pass.

**Phase 1 (complete):**
- [x] `BluetoothTransport` server+client connect over RFCOMM on real hardware
- [x] TPack frames sent both ways, data arrives intact
- [x] `TransportKind` returned correctly by both transport types

**Phase 2 (complete):**
- [x] Unexpected socket drop → both sides reconnect automatically, same channel/stream objects
- [x] Post-reconnect send on same instances → no re-handshake needed
- [x] Explicit `disconnect()` → clean teardown
- [x] `activeTransportCount` ref-counting → `reset()` only on last disconnect

**Phase 3 (implemented; ✓ = covered by the in-process `Phase3.ManualTest`, ⌁ = covered by the two-endpoint hardware harness below, ☐ = not yet automated):**
- [x] BT_MAGIC sent over BT and the server mints `sessionToken` on receipt (✓ coordinator test)
- [x] `sessionToken` set/retrieved/cleared by `reset()` (✓)
- [x] Session-control dispatch hook routes session frames, ignores meeting words + bad magic (✓)
- [x] Small payload (≤ 64 KB) → routed to BT (✓)
- [x] Large payload (server) → announces `WIFI_CONNECT_READY` with token + host/port (✓)
- [x] BT_MAGIC carries each side's Wi-Fi IP; peer host stored + exposed via `getPeerWifiIp()` (⌁ harness **H1**)
- [x] End-to-end large payload: `WIFI_CONNECT_REQ` → `READY` → TCP connect → `SESSION_JOIN` / `_ACK`, data over Wi-Fi (⌁ **H3**)
- [x] Small payload stays on BT, Wi-Fi never comes up (⌁ **H2**)
- [x] Routing boundary: exactly 64 KB on BT, 64 KB+1 on Wi-Fi, both intact (⌁ **H4**)
- [x] One channel spans BT → Wi-Fi → BT on a single stream, no reopen (⌁ **H5**)
- [x] 60s idle → Wi-Fi disconnects, BT alive, channel unaffected (⌁ **H6**)
- [x] Large payload after idle → full `WIFI_CONNECT_REQ` flow again, Wi-Fi re-established (⌁ **H6**)
- [x] Invalid SESSION_JOIN token → server rejects without crash, `_wifiActivating` reset for retry (✓ in-process test 7 added 2026-06-18)
- [x] Both transports disconnect → `reset()` called exactly once (✓ in-process test 8 added 2026-06-18)
- [x] BT drops mid-session → channel resumes transparently after RFCOMM reconnect (⌁ harness **H7**; semi-manual — tester disrupts BT during the 30 s DROP_WINDOW)
- [x] Single-transport (Wi-Fi-only) mode completely unaffected (✓ covered by the existing 21-test Wi-Fi suite in "Wi-Fi Server" mode)

**Phase 3 two-endpoint hardware test harness (updated 2026-06-18).** A separate hybrid suite runs on a
paired Windows + Android pair. It does NOT touch the 21 Wi-Fi-only tests.
- **Where:** Python server `TauSync/windows/tau_sync_tests/tests/cursor_test/android_test_server.py`
  (`serve_all_hybrid_tests`, handlers `serve_hybrid_*`); Android client
  `android/app/.../TestTauSyncActivity.java` (`onRunHybridTestsButtonClicked`, `runHybrid*Test`).
- **How to run:** start the Python console and click **"Hybrid (Bluetooth) Server"** (mutually exclusive
  with the Wi-Fi mode — the transport is a process-wide singleton). On the phone, enter the PC's
  Bluetooth MAC, tap **"Connect (Hybrid BT)"** (the discovered Wi-Fi IP auto-fills the IP field), then
  tap **"Run Hybrid Tests (Phase 3)"**. A single PASS/FAIL banner reports the result.
- **Tests:** H1 IP-over-BT discovery, H2 small→BT (Wi-Fi stays down), H3 large→Wi-Fi (SHA-256 verified),
  H4 threshold boundary, H5 single-stream BT→Wi-Fi→BT continuity, H6 60 s idle teardown + re-establish,
  H7 BT-drop mid-session (semi-manual: disrupt BT during the 30 s DROP_WINDOW the server announces).
  H6 is slow (~65 s). Test order is fixed: H2 before any large payload; H6 and H7 run last.
- **Extensibility:** adding another connection-manager type later is one more mode button + one
  `serve_all_*_tests()` on the server, and one run button + suite on the phone.

**Phase 4:**
- [ ] `BleAdvertiser` on Windows — Android `CompanionDeviceManager` shows only TauSync PC
- [ ] Saved address reused on second launch — BLE popup does not appear
- [ ] Bond lost → `BluetoothTransport.connect()` triggers `BleDiscovery` automatically
- [ ] BLE peripheral not supported → `BleAdvertiser.StartAsync()` exits gracefully

**Phase 5:**
- [ ] `newHybridManager()` factory wires up hybrid `ConnectionManager` correctly
- [ ] `newBtManager()` and `newWifiManager()` produce single-transport managers
- [ ] Existing app code using the old `newManager()` / `connect()` API unchanged

# TauSync Protocol Specification (v3.1)

**Project Name:** TauSync (Cross-Platform Smart Connectivity)  
**Philosophy:** Pure Infrastructure Layer — "Dumb Pipe, Smart Routing"  
**Architecture:** 4-Layer Decoupled Communication Stack  
**Target Platforms:** Windows (C# .NET 8) & Android (Java/Kotlin)  
**Byte Order:** Little Endian  
**Transport:** TCP  

---

## 1. Constants & Configuration

All protocol-level constants live in one place (`CoreConfig` on C#). Both platforms **must** use identical values.

| Constant | Value | Description |
|:---|:---|:---|
| `TPackHeaderSize` | `8` | Fixed header: 4B length + 3B TargetID + 1B flags. |
| `CorrelationIdBytes` | `3` | TargetID field width (max value `0xFFFFFF`). |
| `MagicBytes` | `0x54415553` | ASCII "TAUS" — protocol identity in every signaling JSON. |
| `ControlChannelId` | `0` | Reserved TargetID for discovery/handshake frames. |
| `FlagFin` | `0x01` | Bit 0 — final packet of a logical stream. Triggers cleanup. |
| `FlagControl` | `0x02` | Bit 1 — payload is a `TransferRequest` JSON (signaling). |
| `StreamChunkSize` | `65536` | Recommended max payload per data frame (64 KB). |
| `HandshakeTimeoutSeconds` | `30` | Max time to wait for a handshake OK before timing out. |
| `DefaultPort` | `8888` | TCP port used by `SocketTransport`. |
| `ClientConnectRetryDelaySeconds` | `2` | Delay between TCP connection retries (client mode). |
| `IdRecycleDelayMs` | `2000` | Grace period before a released ID is eligible for reuse (prevents stale-FIN corruption). |
| `MaxPendingDiscoveryPerWord` | `64` | Max queued REQs per word before the service is registered. |

### Valid ID Range

Local IDs range from **1** to **0xFFFFFF** (16,777,215). ID **0** is reserved for the control channel and must never be assigned to a logical stream.

---

## 2. Binary Frame Format (TPack)

Every message on the wire is a **TPack**: a fixed 8-byte header followed by a variable-length payload.

```
Offset  Size  Field         Encoding
──────  ────  ────────────  ────────────────────────────────
0       4B    PayloadLength Little-Endian uint32
4       3B    TargetID      Little-Endian uint24
7       1B    Flags         Bitmask (see below)
8       NB    Payload       Raw bytes (N = PayloadLength)
```

### 2.1 Header Fields

**PayloadLength** (bytes 0–3): Number of bytes that follow the header. A frame with zero payload is valid (used for FIN).

**TargetID** (bytes 4–6): The **receiver's local ID**. Always the ID assigned by the destination side, never the sender's own ID.
- `0` = control channel (discovery/handshake).
- `1..0xFFFFFF` = routed to the handler registered for that ID.

**Flags** (byte 7):

| Bit | Mask | Name | Meaning |
|:----|:-----|:-----|:--------|
| 0 | `0x01` | FIN | Last frame for this stream. Receiver must clean up the handler, routing entries, and release the ID. |
| 1 | `0x02` | CONTROL | Payload is a JSON `TransferRequest` (signaling). When unset, payload is opaque binary data. |
| 2–7 | | Reserved | Must be `0`. |

### 2.2 Frame Construction (BuildFrame)

```
Input:  targetId (int), payload (byte[]), flags (byte)
Output: byte[8 + payload.Length]

header[0..3] = payload.Length        (LE uint32)
header[4..6] = targetId             (LE uint24)
header[7]    = flags
frame        = header ++ payload
```

### 2.3 Frame Parsing (ParseFrame)

```
Input:  rawPacket (byte[])
Assert: rawPacket.Length >= 8
Assert: rawPacket.Length == 8 + PayloadLength

payloadLength = LE_uint32(rawPacket[0..3])
targetId      = LE_uint24(rawPacket[4..6])
flags         = rawPacket[7]
payload       = rawPacket[8 .. 8+payloadLength]
```

### 2.4 Reading Frames from TCP

TCP is a byte stream. The receiver must:

1. **Read exactly 8 bytes** (the header).
2. Parse `PayloadLength` from bytes 0–3.
3. **Read exactly `PayloadLength` bytes** (the payload).
4. Concatenate header + payload → one complete frame.

This is implemented as `ReadExactlyAsync(stream, buffer, offset, count)` which loops `stream.ReadAsync` until `count` bytes are accumulated or EOF.

---

## 3. Signaling Model (TransferRequest)

Discovery and handshake use JSON payloads inside **control frames** (TargetID=0, Flags=CONTROL).

```json
{
  "MagicBytes": 1413567827,
  "SenderID":   <int>,
  "Type":       "<string>",
  "Status":     "REQ" | "OK" | "REJECT"
}
```

| Field | Type | Description |
|:---|:---|:---|
| `MagicBytes` | `uint32` | Must be `0x54415553` (decimal `1413567827`). Protocol identity check. |
| `SenderID` | `int` | The **local ID of the sender** — the ID the peer should target when sending frames back. Range: 1..0xFFFFFF. |
| `Type` | `string` | The **Meeting Word** (e.g. `"CLIPBOARD"`, `"FILE"`, `"main"`). Case-insensitive matching. Required for `REQ`, echoed back in `OK`. |
| `Status` | `string` | `"REQ"` = initiate, `"OK"` = accept, `"REJECT"` = deny. |

### 3.1 Validation Rules

A `TransferRequest` is valid when:
1. `MagicBytes == 0x54415553`
2. `SenderID` is in range `[0, 0xFFFFFF]`
3. `Status` is one of `REQ`, `OK`, `REJECT` (case-insensitive after trim)
4. If `Status == "REQ"`, then `Type` must be non-empty

---

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                     │
│            (Python, Java, or any consumer)               │
│                                                         │
│   stream = manager.Connect("CLIPBOARD")                 │
│   stream.Write(data) / stream.Read(buf)                 │
│   stream.Dispose()                                      │
└──────────────────┬──────────────────────────────────────┘
                   │  Stream (duplex)
┌──────────────────▼──────────────────────────────────────┐
│              IConnectionManager                          │
│                (ConnectionManager)                        │
│                                                         │
│  - Connect(word) → handshake + race resolution → Stream │
│  - SendStreamData / CompleteStream                      │
│  - Owns ProtocolHandler for frame building              │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│              ConnectionContext (Singleton)                │
│                                                         │
│  - ID management (reserve / release / recycle)          │
│  - _routingMap: localId → handler(payload, flags)       │
│  - _targetMap:  localId → peerId                        │
│  - _serviceRegistry: word → callback                    │
│  - Dispatch(targetId, payload, flags)                   │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│              ITransport (SocketTransport)                 │
│                                                         │
│  - TCP client/server                                    │
│  - SendRaw(frame)                                       │
│  - ReceiveLoopAsync → parse frames → Dispatch           │
└─────────────────────────────────────────────────────────┘
```

---

## 5. Interface Contracts

### 5.1 ITransport

Manages the physical TCP connection. One instance per medium (singleton).

| Method | Signature | Description |
|:---|:---|:---|
| `Connect` | `Task Connect(string? targetId)` | `targetId` = IP → client mode (connect to peer). `null`/`""` → server mode (listen for one client). |
| `SendRaw` | `Task SendRaw(byte[] data)` | Send a complete TPack frame (header + payload). Thread-safe via internal send lock. |
| `IsConnected` | `bool IsConnected()` | Connection status. |
| `OnDataReceived` | `event EventHandler<byte[]>` | Fired for unhandled control frames only (handled frames go through `ConnectionContext.Dispatch`). |

#### Transport Behavior

- **Server mode**: Binds to `0.0.0.0:DefaultPort`, accepts **one** TCP client, then stops listening.
- **Client mode**: Retries connection every `ClientConnectRetryDelaySeconds` until success or disposal.
- **Receive loop**: Runs in a background task. Reads frames using `IProtocolHandler.GetHeaderSize()` and `GetPayloadLength()`, then dispatches via `ConnectionContext.Instance.Dispatch()`.
- **Send lock**: A `SemaphoreSlim(1,1)` serializes writes to prevent interleaved frames on the TCP stream.
- **IsServerMode**: Exposed as a `bool` property. Used by `ConnectionManager` for the simultaneous-connect tiebreaker (see §7.3).

### 5.2 IProtocolHandler

Framing, parsing, and handshake — the "how" of data flow.

| Method | Signature | Description |
|:---|:---|:---|
| `GetHeaderSize` | `int GetHeaderSize()` | Returns `8` (TPack header size). |
| `GetPayloadLength` | `int GetPayloadLength(byte[] header)` | Reads LE uint32 from bytes 0–3 of the header. |
| `IsControlFrame` | `bool IsControlFrame(int targetId, byte flags)` | Returns `true` when `targetId == 0`. |
| `BuildFrame` | `byte[] BuildFrame(int targetId, byte[] payload, byte flags)` | Constructs header + payload. |
| `ParseFrame` | `(int, byte[], byte) ParseFrame(byte[] rawPacket)` | Returns `(targetId, payload, flags)`. |
| `SendHandshakeAsync` | `Task<TransferRequest?> SendHandshakeAsync(...)` | Builds and sends a signaling frame, then awaits a response payload and parses it. |

### 5.3 IConnectionManager

The public API consumed by applications.

| Method | Signature | Description |
|:---|:---|:---|
| `Initialize` | `void Initialize(ITransport transport)` | Binds to a transport. Called once. |
| `ConnectTransport` | `Task ConnectTransport(string? targetId)` | Delegates to `ConnectionContext.InitializeTransports`. |
| `IsConnected` | `bool IsConnected()` | Transport status. |
| `Connect` | `Task<Stream> Connect(string word)` | Symmetric connect — both sides call this with the same word. Returns a duplex `Stream`. |
| `SendStreamData` | `void SendStreamData(int localId, byte[] buffer, int offset, int count)` | Sends data over an existing stream. Throws `InvalidOperationException` if no peer route exists. |
| `SendStreamDataAsync` | `Task SendStreamDataAsync(...)` | Async version of `SendStreamData`. |
| `CompleteStream` | `void CompleteStream(int localId)` | Sends FIN and releases the local ID. |
| `ErrorOccurred` | `event EventHandler<Exception>` | Error notifications. |

### 5.4 ISecureChannel (Not Yet Integrated)

Defined for future AES-GCM payload encryption. Currently implemented (`SecureChannel.cs`) but **not wired** into the frame pipeline. When integrated:
- `Encrypt(plaintext)` → `[IV 12B] + [Ciphertext] + [Tag 16B]`
- `Decrypt(ciphertextWithIv)` → plaintext
- Encryption applies to the **payload only** (header is always plaintext).

---

## 6. ConnectionContext — The Central Hub

`ConnectionContext` is a **process-wide singleton**. It owns all routing state and the transport instance.

### 6.1 Internal State

| Structure | Type | Key → Value | Purpose |
|:---|:---|:---|:---|
| `_routingMap` | `ConcurrentDictionary<int, Action<byte[], byte>>` | localId → handler | Incoming frame dispatch. Handler receives `(payload, flags)`. |
| `_targetMap` | `ConcurrentDictionary<int, int>` | localId → peerId | Outgoing: when writing via `localId`, the TPack header uses `peerId` as TargetID. |
| `_serviceRegistry` | `ConcurrentDictionary<string, Action<int,int,Stream>>` | word → callback | Registered listeners for Meeting Words. Case-insensitive. |
| `_pendingDiscoveryByWord` | `ConcurrentDictionary<string, ConcurrentQueue<byte[]>>` | word → queue of REQ payloads | Buffers REQ frames that arrive before the service is registered. Drained on `RegisterService`. |
| `_releasedIds` | `ConcurrentDictionary<int, byte>` | id → 0 | Pool of IDs available for reuse (set semantics, idempotent add). |
| `_nextCorrelationId` | `int` (atomic) | — | Monotonically incrementing ID counter. Starts at 1. |

### 6.2 ID Management

**ReserveId():**
1. Try to take a recycled ID from `_releasedIds` (iterate keys, `TryRemove` first match).
2. If none available, atomically increment `_nextCorrelationId`.
3. If counter exceeds `MaxId` (0xFFFFFF), wrap to `MinId` (1).

**ReleaseId(id):**
1. Remove from `_routingMap` and `_targetMap` immediately.
2. Schedule `RecycleIdAfterDelayAsync(id)` — after `IdRecycleDelayMs` (2 seconds), add to `_releasedIds`.
3. The delay prevents a stale FIN frame (still in-flight from the peer) from corrupting a new handler registered with the same recycled ID.
4. `_releasedIds[id] = 0` is idempotent — safe if `ReleaseId` is called multiple times for the same ID (e.g., from both FIN dispatch and `CompleteStream`).

### 6.3 Frame Dispatch

```
Dispatch(targetId, payload, flags):
    if targetId > 0:
        → DispatchToExistingChannel(targetId, payload, flags)
    if targetId == 0:
        → DispatchDiscoveryRequest(payload, flags)
```

**DispatchToExistingChannel(targetId, payload, flags):**
1. Look up handler in `_routingMap[targetId]`. If missing → return false (frame dropped).
2. Invoke `handler(payload, flags)`.
3. If `flags & FIN`:
   - Remove from `_routingMap[targetId]` and `_targetMap[targetId]`.
   - Call `ReleaseId(targetId)`.
4. Return true.

**DispatchDiscoveryRequest(payload, flags):**
1. Require `flags & CONTROL`. Otherwise → return false.
2. Parse JSON → `TransferRequest`. Validate `MagicBytes`, `Status == "REQ"`.
3. Look up `Type` (word) in `_serviceRegistry`.
4. **If not found**: queue the raw payload in `_pendingDiscoveryByWord[word]` (max 64 per word). Return true.
5. **If found**: call `CompleteDiscoveryHandshake(request, callback)`.

**CompleteDiscoveryHandshake(request, callback):**
1. `localId = ReserveId()`
2. `_targetMap[localId] = request.SenderID`
3. Create `BackBufferedStream`, register an incoming-channel handler in `_routingMap[localId]`.
4. Schedule `callback(localId, peerSenderId, stream)` on `Task.Run` (so it doesn't block the receive loop).

### 6.4 Pending Discovery Queue

Handles the case where Peer A sends `REQ("word")` before Peer B has called `Connect("word")`:

- **On REQ arrival**: if `_serviceRegistry` has no entry for the word, the raw payload is enqueued in `_pendingDiscoveryByWord[word]`.
- **On `RegisterService(word, callback)`**: after storing the callback, `DrainPendingDiscovery(word)` dequeues all buffered payloads and processes each through `CompleteDiscoveryHandshake`.

This ensures the handshake completes regardless of which side calls `Connect` first.

---

## 7. Connect Handshake — Symmetric "Meeting Word" Protocol

Both peers call `Connect(word)` with the same word. There is no explicit "server listens, client connects" at the application level — both sides are symmetric. The pairing produces a duplex `Stream` on each side.

### 7.1 Connect Flow (Single Side)

When `ConnectionManager.Connect(word)` is called:

1. **Register word listener**: `ConnectionContext.RegisterService(word, callback)`. The callback will handle incoming REQs for this word (sends OK back, creates a stream, and writes it to a per-word `Channel<Stream>`).

2. **Create outgoing attempt**: Reserve a `localId`, create a `BackBufferedStream`, register a handler in `_routingMap[localId]` that:
   - On CONTROL flag: complete a `TaskCompletionSource<byte[]>` (the OK response).
   - On data: enqueue into the `BackBufferedStream`.
   - On FIN: complete the `BackBufferedStream`.

3. **Send REQ**: Build and send `TPack(TargetID=0, Flags=CONTROL)` with JSON `{MagicBytes, SenderID=localId, Type=word, Status="REQ"}`.

4. **Resolve race** (see §7.3): Wait for either the OK response (own path) or an incoming stream from the peer's REQ (peer path).

### 7.2 What Happens on the Other Side

When the peer's REQ arrives at TargetID=0:
1. `DispatchDiscoveryRequest` parses it.
2. `_serviceRegistry[word]` → callback → `CompleteDiscoveryHandshake`:
   - Reserves `incomingLocalId`.
   - Maps `_targetMap[incomingLocalId] = peerSenderID`.
   - Creates `BackBufferedStream` + handler for `incomingLocalId`.
   - Callback runs on `Task.Run`:
     - Builds OK response: `{MagicBytes, SenderID=incomingLocalId, Type=word, Status="OK"}`.
     - Sends it as `TPack(TargetID=peerSenderID, Flags=CONTROL)`.
     - Creates `DuplexStream(backStream, incomingLocalId, manager)`.
     - Writes the DuplexStream to the per-word `Channel<Stream>`.

### 7.3 Simultaneous-Connect Race Resolution

When **both** sides call `Connect(word)` at the same time, each side ends up with **two candidate streams**:

| Path | Created by | Stream reads from | Stream writes to |
|:---|:---|:---|:---|
| **Own path** | Received OK response to our REQ | Our outgoing `BackBufferedStream` (localId from `CreateConnectAttempt`) | `_targetMap[ourLocalId]` = peer's incoming localId |
| **Peer path** | Peer's REQ triggered our service callback | Our incoming `BackBufferedStream` (localId from `CompleteDiscoveryHandshake`) | `_targetMap[incomingLocalId]` = peer's outgoing localId |

**Critical constraint**: For data to flow correctly, one side must use the own path and the other must use the peer path. If both pick the same path, data is written to a `BackBufferedStream` that nobody reads.

**Deterministic tiebreaker — transport role**:

```
preferOwnPath = NOT IsTransportServerMode
```

- **TCP client** (`IsTransportServerMode = false`) → prefers **own path** (awaits OK to its REQ).
- **TCP server** (`IsTransportServerMode = true`) → prefers **peer path** (awaits the stream from the word channel).

Since there is always exactly one TCP client and one TCP server, they always pick **complementary** paths. If the preferred path fails (timeout, error), the other path is used as a fallback.

#### Cleanup of the Losing Path

- **When own path wins** (TCP client): The peer-path `DuplexStream` sits in the word channel, unconsumed. Its handler remains in `_routingMap` but nobody sends to it (the peer writes to our outgoing localId, not our incoming localId). Minor resource leak, no data corruption.
- **When peer path wins** (TCP server): `CleanupLosingOutgoingAttempt` is called — releases the outgoing `localId`, unregisters its handler, and disposes its `BackBufferedStream`.

### 7.4 Handshake Timeout

A `CancellationTokenSource` with `HandshakeTimeoutSeconds` is created at the start of race resolution. On expiry, it sets an exception on the outgoing attempt's `TaskCompletionSource`, which causes the await to throw, falling through to the fallback path or propagating the timeout.

---

## 8. Data Streaming

After `Connect(word)` returns a `Stream`, the application reads and writes through it. Under the hood this is a `DuplexStream`.

### 8.1 DuplexStream

A `System.IO.Stream` subclass:
- **Read** → delegates to `BackBufferedStream.Read` (the internal buffer receiving incoming TPack payloads).
- **Write** → calls `ConnectionManager.SendStreamData(localId, buffer, offset, count)`:
  1. Look up `peerId = _targetMap[localId]`. If null → throw `InvalidOperationException`.
  2. Copy the data slice.
  3. Build TPack: `BuildFrame(peerId, chunk, flags=0)`.
  4. `transport.SendRaw(frame)`.
- **Dispose** → calls `ConnectionManager.CompleteStream(localId)`:
  1. Look up `peerId`. If found, send `TPack(TargetID=peerId, payload=empty, Flags=FIN)`.
  2. Call `ReleaseId(localId)`.
  3. Dispose the read stream.

### 8.2 BackBufferedStream

An unbounded internal buffer bridging packet-oriented receive to stream-oriented read:

- **WriteChunk(byte[])**: Enqueues a byte array into a `Channel<byte[]>`.
- **Complete()**: Marks the channel as complete (no more writes). Idempotent via `TryComplete()`.
- **Read / ReadAsync**: 
  1. Copy from the current partially-consumed chunk if available.
  2. If more data is needed, try to dequeue the next chunk without blocking.
  3. **If some bytes were already copied, return immediately** (standard stream semantics — don't block for more data when partial data is available).
  4. If no bytes read yet, block/await on `channel.Reader.ReadAsync` for the next chunk.
  5. On `ChannelClosedException` (stream completed), return bytes read so far (0 = EOF).

### 8.3 Sending Data — Frame Segmentation

`SendStreamData` sends the exact bytes provided. The application is responsible for segmentation if payloads exceed `StreamChunkSize` (64 KB). `SendStreamDataAsync` is the async variant.

Both methods throw `InvalidOperationException` if no peer route exists for the given `localId` and `count > 0`, making connection issues explicit rather than silently dropping data.

---

## 9. Stream Teardown & FIN Protocol

### 9.1 Initiator Side (Dispose)

1. Application calls `stream.Dispose()`.
2. `DuplexStream.Dispose()` → `ConnectionManager.CompleteStream(localId)`:
   - Look up `peerId` from `_targetMap[localId]`.
   - If found: send `TPack(TargetID=peerId, Payload=empty, Flags=FIN)`.
   - Call `ReleaseId(localId)` → clears maps, schedules delayed ID recycle.
3. Dispose the backing `BackBufferedStream`.

### 9.2 Receiver Side (FIN Arrival)

1. `DispatchToExistingChannel` receives frame with `FIN` flag.
2. Invokes the handler → `BackBufferedStream.Complete()`.
3. Removes from `_routingMap`, `_targetMap`, calls `ReleaseId`.
4. Application's next `Read` returns 0 bytes (EOF).
5. Application calls `stream.Dispose()` → `CompleteStream`:
   - `_targetMap` already cleared → `peerId` is null → FIN not sent again (no double-FIN).
   - `ReleaseId` called again (idempotent — delayed recycle uses `ConcurrentDictionary`, duplicate add is harmless).

### 9.3 ID Recycling Safety

Released IDs are **not** immediately available for reuse. After `ReleaseId`:
1. Maps are cleared instantly (no routing to dead handlers).
2. After `IdRecycleDelayMs` (2 seconds), the ID is added to the recycle pool.
3. This grace period ensures any in-flight FIN frames from the peer are fully processed before the ID can be claimed by a new `Connect` call, preventing a stale FIN from corrupting a new handler.

---

## 10. Execution Flow — Complete Example

### Scenario: Both Peers Connect on "CLIPBOARD"

```
Peer A (TCP Client)                          Peer B (TCP Server)
═══════════════════                          ═══════════════════

1. Connect("CLIPBOARD")                      1. Connect("CLIPBOARD")
   RegisterService("CLIPBOARD", cb_A)           RegisterService("CLIPBOARD", cb_B)
   ReserveId() → localId_A = 1                  ReserveId() → localId_B = 1
   handler_A registered for ID 1                 handler_B registered for ID 1
   Send REQ(TargetID=0, SenderID=1,             Send REQ(TargetID=0, SenderID=1,
            Type="CLIPBOARD")                             Type="CLIPBOARD")

──── REQ from A arrives at B ────────────────────────────────────────
2. B: DispatchDiscoveryRequest
   cb_B fires → CompleteDiscoveryHandshake:
     ReserveId() → inc_B = 2
     _targetMap[2] = 1 (A's SenderID)
     handler for ID 2 registered
     Task.Run → HandleWordRequest:
       Send OK(TargetID=1, SenderID=2, Status="OK") → to A
       DuplexStream(backStream_2, localId=2) → channel_B

──── REQ from B arrives at A ────────────────────────────────────────
3. A: DispatchDiscoveryRequest
   cb_A fires → CompleteDiscoveryHandshake:
     ReserveId() → inc_A = 2
     _targetMap[2] = 1 (B's SenderID)
     handler for ID 2 registered
     Task.Run → HandleWordRequest:
       Send OK(TargetID=1, SenderID=2, Status="OK") → to B
       DuplexStream(backStream_2, localId=2) → channel_A

──── OK from B arrives at A ─────────────────────────────────────────
4. A: handler_A(ID=1) receives CONTROL payload
   Parses OK: SenderID=2 (B's inc_B)
   _targetMap[1] = 2
   Own path stream: DuplexStream(backStream_1, localId=1)

──── OK from A arrives at B ─────────────────────────────────────────
5. B: handler_B(ID=1) receives CONTROL payload
   Parses OK: SenderID=2 (A's inc_A)
   _targetMap[1] = 2
   Own path stream: DuplexStream(backStream_1, localId=1)

──── Race Resolution ────────────────────────────────────────────────
6. A (TCP client, preferOwnPath=true):
   → Uses own path: DuplexStream(localId=1), writes to peerId=2

   B (TCP server, preferOwnPath=false):
   → Uses peer path: DuplexStream(localId=2), writes to peerId=1
   → CleanupLosingOutgoingAttempt(localId=1)

──── Data Phase ─────────────────────────────────────────────────────
7. A writes "Hello":
   SendStreamData(1) → peerId=2 → TPack(TargetID=2, Flags=0, "Hello")
   B: handler for ID 2 → backStream_2.WriteChunk("Hello")
   B reads from backStream_2 → "Hello" ✓

8. B writes "World":
   SendStreamData(2) → peerId=1 → TPack(TargetID=1, Flags=0, "World")
   A: handler for ID 1 → backStream_1.WriteChunk("World")
   A reads from backStream_1 → "World" ✓

──── Teardown ───────────────────────────────────────────────────────
9. A: stream.Dispose() → CompleteStream(1)
   Send TPack(TargetID=2, Flags=FIN)
   ReleaseId(1) → maps cleared, ID recycle in 2s

10. B: receives FIN at ID 2
    backStream_2.Complete() → B reads EOF
    B: stream.Dispose() → CompleteStream(2)
    _targetMap[2] already cleared → no FIN sent back
    ReleaseId(2) → maps cleared, ID recycle in 2s
```

---

## 11. Thread Safety & Concurrency Model

| Resource | Mechanism |
|:---|:---|
| `_routingMap`, `_targetMap`, `_serviceRegistry` | `ConcurrentDictionary` — lock-free reads, fine-grained locking on writes. |
| `_nextCorrelationId` | `Interlocked.Increment` — atomic. |
| `_releasedIds` | `ConcurrentDictionary<int,byte>` — set semantics, idempotent add. |
| TCP send | `SemaphoreSlim(1,1)` in `SocketTransport` — serializes frame writes. |
| Receive loop | Single background `Task` reads frames sequentially. |
| Service callbacks | Dispatched on `Task.Run` to avoid blocking the receive loop. |
| `BackBufferedStream` | `Channel<byte[]>` (unbounded) — thread-safe producer/consumer. |
| `DuplexStream` | Read and write are independent — reads come from `BackBufferedStream`, writes go through `SendStreamData`. No shared mutable state between the two directions. |

---

## 12. Implementation Checklist for Java (Android)

The Java implementation must be **wire-compatible** with the C# side. This means:

### 12.1 Must Match Exactly

- [ ] TPack header format: 4B LE length + 3B LE TargetID + 1B flags.
- [ ] `TransferRequest` JSON field names: `MagicBytes`, `SenderID`, `Type`, `Status` (exact casing, PascalCase).
- [ ] `MagicBytes` value: `0x54415553`.
- [ ] Flag values: FIN=`0x01`, CONTROL=`0x02`.
- [ ] TargetID=0 for all discovery/handshake frames.
- [ ] OK response targets the REQ's `SenderID`.
- [ ] ID range: 1..0xFFFFFF.
- [ ] Port: 8888 (configurable).

### 12.2 Must Implement (Behavioral)

- [ ] **ReadExactly**: TCP read loop that accumulates exactly N bytes before returning.
- [ ] **Frame reassembly**: Read 8-byte header, then PayloadLength bytes.
- [ ] **Dispatch by TargetID**: 0 → discovery, >0 → handler lookup.
- [ ] **Symmetric Connect(word)**: RegisterService + send REQ + race resolution.
- [ ] **Race resolution tiebreaker**: TCP server prefers peer path, TCP client prefers own path.
- [ ] **Pending discovery queue**: Buffer REQs when service not yet registered.
- [ ] **ID recycling with grace period**: Don't reuse an ID for at least 2 seconds after release.
- [ ] **FIN handling**: On receive → complete stream + cleanup. On send → empty payload + FIN flag.
- [ ] **BackBufferedStream equivalent**: Producer/consumer buffer that bridges packets to stream reads. Return partial data immediately (don't block waiting to fill the entire read buffer).
- [ ] **Send lock**: Serialize TCP writes to prevent frame interleaving.

### 12.3 May Differ (Platform-Specific)

- Singleton pattern (Java static instance vs C# static readonly).
- Async model (Java `CompletableFuture`/threads vs C# `Task`/`async-await`).
- Channel implementation (Java `BlockingQueue` or `LinkedTransferQueue` vs C# `Channel<T>`).
- Transport discovery (Android may use Bluetooth in addition to WiFi/TCP).

---

## 13. Implementation Notes

### 13.1 Why Transport-Role Tiebreaker?

In simultaneous connect, each side creates two local IDs (outgoing attempt + incoming from peer's REQ). The "own path" stream reads from the outgoing `BackBufferedStream`, and the "peer path" stream reads from the incoming `BackBufferedStream`. The peer writes to whichever ID was in the OK response it received.

If both sides choose "own path", the peer writes to the incoming ID's `BackBufferedStream`, but the app reads from the outgoing ID's `BackBufferedStream` — data goes to the wrong buffer. The transport-role tiebreaker guarantees complementary choices without any extra protocol messages.

### 13.2 Why Delayed ID Recycling?

When Side A disposes a stream (localId=1) and immediately starts a new `Connect` that recycles localId=1, Side B might still have an in-flight FIN targeting localId=1 from the old stream. If this FIN arrives after the new handler is registered for localId=1, it would destroy the new handler and break the new connection. The 2-second grace period ensures all in-flight frames are processed before the ID becomes available.

### 13.3 BackBufferedStream Partial-Read Semantics

Standard `Stream.Read` contract: return immediately if **any** data is available, even if fewer bytes than requested. This is critical — if the caller requests 1024 bytes but only 50 arrived (e.g., a short HTTP request), the read must return 50 bytes, not block waiting for 974 more.

### 13.4 Pending Discovery Queue vs Registration Order

The queue handles the case where Peer A sends REQ("word") before Peer B has called `Connect("word")`. Without the queue, the REQ would be dropped (no service registered), and the handshake would never complete. The queue stores up to 64 REQs per word, draining them when `RegisterService` is called.

### 13.5 Security Layer (Future)

`SecureChannel` (AES-256-GCM) is implemented but not yet wired into the pipeline. When activated:
- Encryption happens **after** `BuildFrame` (encrypt the payload only, header stays plaintext).
- Decryption happens **before** `Dispatch` (decrypt the payload, pass plaintext to handlers).
- Key exchange mechanism is TBD (likely Diffie-Hellman during transport connection).

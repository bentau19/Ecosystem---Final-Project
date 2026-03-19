# TauSync v3.0 — C# Implementation Plan

This document maps the **TauSync_Protocol_Spec.md (v3.0)** to concrete C# changes.

---

## 0. Implementation Emphases (read before writing code)

### 0.1 Dispatch: check order

**Always branch first on TargetID.**

- **If TargetID == 0:** This is discovery/handshake. **Require** the CONTROL bit to be set **and** valid MagicBytes. Reject or ignore otherwise.
- **If TargetID > 0:** Do **not** branch on CONTROL here. Forward the packet (payload + flags) to the **relevant handler** from _routingMap. The **handler itself** decides whether the payload is DATA or in-band CONTROL (e.g. an error message mid-stream). The context only routes; it does not interpret CONTROL for targetId > 0.

### 0.2 Resource cleanup on FIN

When a TPack is received with **FIN flag** set, the corresponding ID must be released from **both** _routingMap **and** _targetMap, and the ID must be returned to the pool (ReleaseId). Failing to remove the ID from both maps leads to "leaks" of held IDs and prevents reuse.

### 0.3 Stream returned by Connect: queue-based

The Stream returned by `Connect(word)` must support **CopyToAsync**-style consumption (like in Node.js). Implement it as a **queue-based** stream:

- **Dispatch** pushes incoming payloads (and FIN) into a **queue/channel** (e.g. `Channel<byte[]>` or a thread-safe queue).
- The **Stream** implementation **pulls** from that queue on Read/ReadAsync.
- So: producer = Dispatch (push to queue), consumer = Stream (pull from queue). This gives backpressure and allows the user to read at their own pace (e.g. `await stream.CopyToAsync(fileStream)`).

---

## 1. Summary of Spec Changes

| Aspect | Old (current C#) | New (v3.0 spec) |
|--------|------------------|-----------------|
| **Signaling** | TransferRequest: CorrelationID, ParentID, Type, Status (REQ/PUSH/APPROVE/OK/REJECT/FIN), FileSize, Payload | TransferRequest: **SenderID**, Type ("Meeting Word"), Status (**REQ**, **OK**, **REJECT** only), MagicBytes |
| **Header** | CorrelationID (3B) — stream ID | **TargetID** (3B) — **receiver’s** local ID (always destination) |
| **Control** | Control = CorrelationID == 0 | Control = **TargetID == 0** for discovery; **Flags bit 1 = CONTROL (0x02)** indicates signaling JSON vs raw payload |
| **Flags** | Bit 0: FIN | Bit 0: FIN (0x01), **Bit 1: CONTROL (0x02)** |
| **Manager API** | Connect(targetId), SmartSend, GetStream, RegisterHandler, SetIncomingClipboardHandler, … | **Listen(word, Action<Stream, int> onConnect)** (passive), **Connect(word) → Task<Stream>** (active) |
| **Context** | _routingMap, _peerToLocalMap, _incomingPushHandlersByType | **_routingMap** (LocalID → handler), **_targetMap** (LocalID → PeerID for sending), **_serviceRegistry** (Word → callback) |

---

## 2. Model: TransferRequest.cs

- **Remove:** CorrelationID, ParentID, FileSize, Payload.
- **Add:** **SenderID** (int) — "The Local ID of the Sender (the ID the peer should send back to)".
- **Keep:** MagicBytes, Type, Status.
- **Restrict Status:** Only `REQ`, `OK`, `REJECT`. Validation: Status one of these; Type non-empty when required; SenderID in [0, 0xFFFFFF] (or 1..0xFFFFFF when not discovery).
- **IsValid():** MagicBytes, SenderID range, Status in { REQ, OK, REJECT }, Type non-empty for REQ.

---

## 3. Framing: TPack Header and Flags

- **Rename** header field conceptually: "CorrelationID" → **TargetID** (receiver’s ID). In code we can keep a parameter name `targetId` in BuildFrame/ParseFrame.
- **Define flags in CoreConfig:**  
  `FlagFin = 0x01`, **`FlagControl = 0x02`**.
- **BuildFrame(targetId, payload, flags):** When sending signaling JSON, caller passes `flags |= FlagControl`. No change to header layout; only semantics and flag usage.
- **ParseFrame:** Return `(targetId, payload, flags)`. Callers interpret:
  - `targetId == 0` → discovery/handshake.
  - `(flags & FlagControl) != 0` → payload is TransferRequest JSON; else raw bytes.

---

## 4. ConnectionContext (Singleton)

### 4.1 State

- **ID pool:** Keep `ReserveId()` / `ReleaseId()` (1..0xFFFFFF).
- **_routingMap:** `ConcurrentDictionary<int, ChannelHandler>` where `ChannelHandler` holds:
  - A way to deliver data: e.g. `Stream` (write incoming bytes, complete on FIN) and/or `Action<byte[], byte>` (payload + flags).
  - On **FIN**: remove from _routingMap **and** _targetMap, then call ReleaseId (see §0.2).
- **_targetMap:** `ConcurrentDictionary<int, int>` — LocalID → PeerID. Used when **sending**: for local task `X`, send with header TargetID = _targetMap[X].
- **_serviceRegistry:** `ConcurrentDictionary<string, Action<int, int, Stream>>` — Word → callback(localId, peerSenderId, stream). When REQ arrives on TargetID=0 with Type=word, we look up this callback.

### 4.2 Dispatch(targetId, payload, flags)

**Check TargetID first** (see §0.1).

- **targetId > 0:**
  - Lookup _routingMap[targetId]. If no handler, ignore or log.
  - **Pass (payload, flags) to the handler as-is.** The handler decides whether the payload is DATA or in-band CONTROL (e.g. error mid-stream); the context does not branch on CONTROL here.
  - If `(flags & FlagFin) != 0`: **cleanup** — remove from _routingMap, remove from _targetMap, ReleaseId(targetId) (§0.2).
- **targetId == 0:**
  - **Require** `(flags & FlagControl) != 0` and valid MagicBytes in payload. Otherwise reject/ignore.
  - Parse payload as TransferRequest. Validate MagicBytes, Status == "REQ".
  - Lookup req.Type in _serviceRegistry. If not found: optionally send REJECT.
  - If found:
    - localId = ReserveId().
    - _targetMap[localId] = req.SenderID (peer’s ID to send back to).
    - Create a **queue-based** stream (see §0.3) and register _routingMap[localId] = handler that pushes to the stream and, on FIN, performs cleanup (remove from _routingMap, _targetMap, ReleaseId — §0.2).
    - Invoke _serviceRegistry[word](localId, req.SenderID, stream). Callback (or ConnectionManager) sends OK (TPack TargetID=req.SenderID, Flags=CONTROL, JSON SenderID=localId, Status=OK).

### 4.3 Sending

- **Resolve TargetID for send:** When we have a local task ID `localId`, use **TargetID = _targetMap[localId]** in the TPack header (receiver’s ID = peer’s local ID).
- ConnectionContext can expose e.g. `int? GetPeerIdFor(int localId)` for the manager/transport to build the header.

### 4.4 Remove

- _incomingPushHandlersByType, RegisterIncomingPushHandler, TryGetIncomingPushHandler.
- _peerToLocalMap, LinkPeerIdToLocalTask (replaced by _targetMap and single handshake).

---

## 5. IConnectionManager and ConnectionManager

### 5.1 New interface (per spec §3)

- **Listen(string word, Action<Stream, int> onConnect)**  
  Passive. Registers a "listener" for the Meeting Word. Does not send; when a REQ arrives for this word, the callback is invoked with (stream, localId) after the context has registered the stream and the manager has sent OK.
- **Task<Stream> Connect(string word)**  
  Active. Initiates handshake with TargetID=0, sends REQ(SenderID=ourLocalId, Type=word, Status=REQ); waits for OK; then returns a Stream that:
  - **Read:** data received for our localId (from _routingMap) — the stream must be **queue-based** (see §0.3) so the user can e.g. `CopyToAsync`; Dispatch pushes to the queue, the stream pulls from it.
  - **Write:** sends with header TargetID = _targetMap[localId] (peer’s ID).

### 5.2 Optional compatibility

- **Initialize(ITransport)**, **IsConnected()** — keep for wiring transport.
- **Connect(string? targetId)** for "connect to address" vs "listen" can remain for transport-level connect; the new **Connect(word)** is the application-level "connect by word".
- Deprecate/remove: SmartSend, GetStream, RegisterHandler, UnregisterHandler, SetIncomingClipboardHandler, RegisterIncomingPushHandler. Replace usage with Listen + Connect(word).

### 5.3 Listen implementation sketch

- Register in ConnectionContext._serviceRegistry[word] a callback that:
  - Receives (localId, peerSenderId, stream).
  - Sends OK: TPack(TargetID=peerSenderId, Flags=CONTROL) + JSON(SenderID=localId, Status=OK).
  - Calls onConnect(stream, localId).

### 5.4 Connect(word) implementation sketch

- ReserveId() → localId.
- Send TPack(TargetID=0, Flags=CONTROL) + JSON(SenderID=localId, Type=word, Status=REQ).
- Wait for TPack with TargetID=localId, Flags=CONTROL, payload JSON with Status=OK and SenderID=peerLocalId.
- Set _targetMap[localId] = peerLocalId.
- Create a stream that: (1) reads from _routingMap[localId] (incoming data), (2) writes by sending TPack(TargetID=peerLocalId, payload).
- Return that stream.

---

## 6. IProtocolHandler and ProtocolHandler

- **BuildFrame(int targetId, byte[] payload, byte flags = 0):** Parameter is "target ID" (receiver). Caller sets flags (e.g. FlagControl for signaling).
- **ParseFrame(rawPacket):** Return `(targetId, payload, flags)`. Naming: targetId instead of correlationId.
- **Handshake:** 
  - Sends REQ with SenderID (our local ID), Type=word, Status=REQ.
  - Expects response: TPack with TargetID=our SenderID, CONTROL flag, JSON with Status=OK and SenderID=peer’s local ID (so we can set _targetMap[ourId]=theirId).

---

## 7. SocketTransport

- Keep 8-byte header parsing; treat the 3-byte ID as **TargetID** (receiver).
- When TargetID=0: pass to "control" path (ConnectionManager/Context) with full packet or (targetId, payload, flags).
- When TargetID>0: call ConnectionContext.Instance.Dispatch(targetId, payload, flags).
- No logic change for FIN; optionally respect CONTROL flag if transport needs to distinguish payload type.

---

## 8. CoreConfig

- Add: `public const byte FlagControl = 0x02;`
- Keep: FlagFin = 0x01, ControlChannelId = 0 (for TargetID discovery).

---

## 9. Cleanup Checklist

- [ ] TransferRequest: SenderID only; remove CorrelationID, ParentID, FileSize, Payload; Status REQ/OK/REJECT.
- [ ] CoreConfig: add FlagControl.
- [ ] ConnectionContext: _targetMap; _serviceRegistry; Dispatch logic (TargetID first: 0 → require CONTROL+MagicBytes; >0 → pass to handler, handler decides DATA vs CONTROL); FIN cleanup from both _routingMap and _targetMap (§0.2); remove _peerToLocalMap, _incomingPushHandlersByType.
- [ ] ConnectionContext/Stream: stream returned by Connect and used in Listen must be **queue-based** (Dispatch pushes, Stream pulls) for CopyToAsync support (§0.3).
- [ ] ConnectionManager: implement Listen(word, onConnect) and Connect(word)→Stream; remove/deprecate SmartSend, GetStream, RegisterIncomingPushHandler, SetIncomingClipboardHandler; keep transport init/connect if needed.
- [ ] ProtocolHandler: handshake uses SenderID and TargetID; set CONTROL flag for signaling frames.
- [ ] IConnectionManager: new surface Listen + Connect(word).
- [ ] SocketTransport: use TargetID naming; pass flags through to Dispatch.
- [ ] Python: update server.py / client.py to use Listen("CLIPBOARD", ...) and Connect("CLIPBOARD") (or equivalent) once C# API is in place.

---

## 10. Order of Implementation

1. **Models & constants:** TransferRequest (SenderID, slim down), CoreConfig (FlagControl).
2. **Protocol:** BuildFrame/ParseFrame with targetId and flags; handshake with REQ/OK/REJECT and SenderID.
3. **ConnectionContext:** _targetMap, _serviceRegistry, new Dispatch (targetId==0 vs >0, CONTROL vs data, FIN cleanup).
4. **IConnectionManager + ConnectionManager:** Listen(word, onConnect), Connect(word)→Stream; remove old API step by step.
5. **SocketTransport:** TargetID naming, flags to Dispatch.
6. **Tests / Python:** Adapt server and client to new API.

This keeps the "dumb pipe, smart routing" and "header = receiver ID" rules from the spec and aligns C# with v3.0.

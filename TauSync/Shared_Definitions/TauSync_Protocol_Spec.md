# 🛰️ TauSync Protocol Specification (v3.0)

**Project Name:** TauSync (Cross-Platform Smart Connectivity)
**Project Philosophy:** Pure Infrastructure Layer ("Dumb Pipe, Smart Routing"). 
**Architecture:** 4-Layer Decoupled Communication Stack
**Patterns:** Singleton Transports, Dispatcher/Routing Map, AEAD Security
**Target Platforms:** Windows (C# .NET) & Android (Java/Kotlin)
**Byte Order:** Little Endian
---

## 1. Logic Layer: `TransferRequest` (Signaling)
JSON object used for task coordination (signaling). **TransferRequest is always sent as the payload of a TPack:** the TPack header has **CorrelationID = 0** (so the packet is routed to the control channel), while the **CorrelationID inside the TransferRequest JSON** is the stream ID we are listening to or negotiating (e.g. 101). So: TPack header CorrelationID = 0 → control; TransferRequest body CorrelationID = stream ID.

| Field | Type | Description |
| :--- | :--- | :--- |
| **`MagicBytes`** | `uint32` | `0x54415553` ("TAUS") — protocol identity verification. |
| **`SenderID`** | `int` | The Local ID of the **Sender** (The ID the peer should send back to). |
| **`Type`** | `string` | The "Meeting Word" (e.g., `"CLIPBOARD"`). |
| **`Status`** | `string` | `REQ` (Initial), `OK` (Accept), `REJECT` (Deny). |
---

## 2. Framing Layer: Binary Packet Structure (TPack)
Every network packet consists of a fixed 8-byte header and an encrypted payload.

$$Packet = \underbrace{[Length]}_{4B} + \underbrace{[CorrelationID]}_{3B} + \underbrace{[Flags]}_{1B} + \underbrace{[EncryptedPayload]}_{NB}$$

### Header Layout
* **Length (4B):** Total size of the encrypted payload in bytes (Little Endian).
* **TargetID (3B):** The destination ID (the local ID assigned by the receiver).
    * **`0`**: Reserved for initial discovery/handshake (when the Peer's ID is unknown).
* **Flags (1B): Bitmask for routing and session state.**
    * **Bit 0 (FIN - `0x01`):** Termination signal. Indicates the final packet of a stream; triggers ID release and resource cleanup.
    * **Bit 1 (CONTROL - `0x02`):** Payload Type signal.
        * **Set (1):** Payload is a Signaling JSON (`TransferRequest`).
        * **Unset (0):** Payload is raw binary data (Default state).
    * **Bits 2–7:** Reserved for future use (must be `0`).
---

## 3. Interface Contracts (The Architecture)

### 📡 ITransport (Singleton per Medium)
Manages the physical connection. Implement as a Singleton for each medium (Bluetooth, WiFi).
- `void Connect(string targetId)`: Initializes the connection. **`targetId`** = IP address of the peer.
- `void SendRaw(byte[] data)`: Sends raw binary data.
- `bool IsConnected()`: Returns the current connection status.
- **Event:** `OnDataReceived(byte[] data)`: Triggered when raw bytes arrive.

### 🔐 ISecureChannel (AEAD Security)
Handles AES-GCM encryption. Encrypts/Decrypts **only the Payload**.
- `byte[] Encrypt(byte[] plaintext)`: Returns `[IV (12B)] + [Ciphertext + Tag]`.
- `byte[] Decrypt(byte[] ciphertextWithIv)`: Extracts IV and decrypts the content.

### 📜 IProtocolHandler (Framing & Handshake — "How" data flows)
Manages **how** information flows: framing, parsing, and the full handshake (sending `TransferRequest` JSON on the control channel and waiting for OK/REJECT). Does not decide which transport or when to connect — that is the Manager’s role.
- `byte[] BuildFrame(int correlationId, byte[] payload)`: Constructs the **8-byte** header + payload.
- `(int correlationId, byte[] payload) ParseFrame(byte[] rawPacket)`: Deconstructs an incoming packet.
- **Handshake:** Owns sending JSON requests on **CorrelationID = 0** and receiving ACK responses ("OK"/"REJECT"); may expose methods such as `SendRequestAsync`, `WaitForAckAsync` (or equivalent).

### 🧠 `IConnectionManager` (The Entry Point / Gateway)
The high-level API for external processes (Python/Java).
- `void Listen(string word, Action<Stream, int> onConnect)`: **Passive Mode.** Registers a callback for a specific "Meeting Word". Does not send network data.
- `Task<Stream> Connect(string word)`: **Active Mode.** Initiates a handshake with `TargetID: 0` and returns a usable stream.

---

## 4. The Central Hub: `ConnectionContext` (Singleton)
The internal Switchboard. Manages IDs and routes packets without understanding application logic.

### Internal State:
1.  **ID Pool:** Thread-safe generator for local IDs (1..0xFFFFFF).
2.  **`_routingMap` (LocalID -> Handler):** Determines where to deliver incoming packets. Since the header contains our `TargetID`, routing is a direct $O(1)$ lookup.
3.  **`_targetMap` (LocalID -> PeerID):** Used for **Sending**. When we write to our local task $X$, we look up the peer's ID $Y$ to put in the TPack `TargetID` header.
4.  **`_serviceRegistry` (Word -> Callback):** Stores listeners waiting for a connection on a specific word.

### Receiving Logic (`Dispatch`):
1.  **If `TargetID > 0`:**
    * Directly fetch the handler from `_routingMap[TargetID]`.
    * If `Flag & CONTROL`: Decrypt and pass JSON to the task logic.
    * Else: Pass raw bytes directly to the associated `Stream`.
2.  **If `TargetID == 0`:**
    * Must have `Flag & CONTROL`.
    * Verify `MagicBytes` and `Status == "REQ"`.
    * Lookup `Type` (Meeting Word) in `_serviceRegistry`.
    * If found: 
        * `LocalID = ReserveID()`.
        * **Bind:** `_targetMap[LocalID] = SenderID` (from JSON).
        * Register `LocalID` in `_routingMap`.
        * Trigger the listener callback.

---

## 5. Execution Flow (The "Address Marriage")

### Phase A: The Handshake
1.  **Initiator (Android):** Reserves `LocalID: 500`. Sends `TPack(TargetID: 0, Flags: CONTROL)` + `JSON(SenderID: 500, Type: "CLIPBOARD", Status: "REQ")`.
2.  **Receiver (PC):** `Dispatch` sees `TargetID: 0`. Matches word `"CLIPBOARD"`. 
    * Reserves `LocalID: 101`.
    * **Maps:** `_targetMap[101] = 500` (Our 101 talks to their 500).
3.  **Receiver (PC):** Sends `TPack(TargetID: 500, Flags: CONTROL)` + `JSON(SenderID: 101, Status: "OK")`.
4.  **Initiator (Android):** Receives `TargetID: 500`. Parses JSON, sees `SenderID: 101`.
    * **Maps:** `_targetMap[500] = 101` (Our 500 talks to their 101).

### Phase B: Data Streaming
1.  **Android sends Data:** Uses `TargetID: 101` (from its `_targetMap`) and `Flags: 0x00`.
2.  **PC receives:** `Dispatch` sees `TargetID: 101`. 
3.  **PC routes:** Directly pushes bytes to Task 101's Stream. **No more JSON parsing.**

---

## 6. Implementation Guidelines for Cursor
* **Header Sovereignty:** The ID in the TPack header is ALWAYS the ID of the **Receiver**.
* **Encapsulation:** `ConnectionContext` should not know about "Files" or "Clipboard". It only manages `Stream` and `byte[]`.
* **Thread Safety:** Use `ConcurrentDictionary` and `Interlocked` for all internal maps and ID generation.
* **Cleanup:** Upon receiving a TPack with `Flag: FIN (0x01)`, the `ConnectionContext` must remove the entry from both `_routingMap` and `_targetMap` and release the ID.
# 🛰️ TauSync Protocol Specification (v3.0)

**Project Name:** TauSync (Cross-Platform Smart Connectivity)
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
| **`CorrelationID`** | `int` | Unique identifier of the message sender (odd/even rule); this is the stream ID we are listening to or negotiating. |
| **`Type`** | `string` | Task type; defined by the end user/Handler (examples: `"FILE"`, `"CLIPBOARD"`, `"BACKUP"`). |
| **`Status`** | `string` | Conversation state: `REQ`, `PUSH`, `APPROVE`, `OK`, `REJECT`, `FIN`. |
| **`FileSize`** | `long` | Total payload size in bytes (64-bit for files > 2GB). |
| **`Payload`** | `string` | Inner JSON with extra data (e.g. `{"FileName": "pic.jpg"}`). |

---

## 2. Framing Layer: Binary Packet Structure (TPack)
Every network packet consists of a fixed 8-byte header and an encrypted payload.

$$Packet = \underbrace{[Length]}_{4B} + \underbrace{[CorrelationID]}_{3B} + \underbrace{[Flags]}_{1B} + \underbrace{[EncryptedPayload]}_{NB}$$

### Header layout
* **Length (4B):** Length of the encrypted payload only (Little Endian). Max packet size will be defined later (chunking algorithm); for now there is no artificial limit, but payload must not exceed the `Length` value in the TPack.
* **CorrelationID (3B):** Stream identifier (in the **TPack header**).
    * **`0`** — **Control channel only:** The packet payload is a **TransferRequest** (JSON, encrypted like any payload). Signaling is carried as TPack with header CorrelationID = 0. The **CorrelationID inside the TransferRequest** body is the stream ID we are listening to or negotiating (e.g. 101).
    * **`X > 0`** — **Channel-specific data:** Any other TPack intended for a specific channel has **CorrelationID = that channel’s ID** (not 0) in the header. The receiver uses the header CorrelationID to look up the Routing Map; the packet is then **routed automatically** to the handler registered for that channel (e.g. Python or Android client). No extra logic — the design guarantees that data for channel X arrives with header CorrelationID = X and goes to the right place.
    * **Sovereignty rule:** IDs generated in **C#** are always **odd**. IDs in **Java** are always **even**.
* **Flags (1B):**
    * **Bit 0 (FIN):** `0x01` indicates the last packet in the stream. Close the handler and remove the entry from the map.
    * **Bits 1–7:** Reserved (padding), currently always `0`; reserved for future use.
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

### 🧠 IConnectionManager (Which connection & when — Dispatcher & Routing Map)
Decides **which** connection type to use (e.g. WiFi vs Bluetooth) and **when** to initiate or use it. Orchestrates the layers and dispatches incoming data to the right client.
- **Routing Map:** `Dictionary<int, Action<byte[]>>`: Maps **CorrelationID** (from the incoming TPack header) to the handler for that channel. **Channel-specific TPack** use the channel’s CorrelationID in the header (not 0); the receiver looks up that ID in the Map and **routes the packet automatically** to the registered handler — no extra logic.
- **Control channel:** All signaling (`TransferRequest` JSON) uses TPack with header **CorrelationID = 0**. After handshake, data for a channel is sent in TPack with header **CorrelationID = that channel** (e.g. 101); those packets are routed automatically to the handler for that channel.
- `Task SmartSend(Stream source, string type, string payload = null)`: 
    - For pushing data (e.g. **CLIPBOARD**). **payload** is optional (e.g. JSON with `FileName`).
    - Performs handshake on ID 0 and streams content on a dedicated ID.
- `Task<Stream> GetStream(string type, string payload = null)`: 
    - For pulling data (e.g. **BACKUP**). **payload** is optional.
    - Performs double handshake on ID 0 and returns a stream ready for asynchronous read.
- `void RegisterHandler(int correlationId, Action<byte[]> callback)`: Registers the client (e.g. Python, Android) that listens for incoming data on that CorrelationID; when TPack arrives with that ID, payload is decrypted and passed to the callback.

---

## 4. Data Flow (The Pipeline)

### Outbound (Sending Data)
1. **Initiation**: `SmartSend` creates a `TransferRequest` (JSON) and sends it as a Handshake via `ProtocolHandler`.
2. **Waiting**: After receiving "OK", the Manager reads from the `Stream` in 64KB chunks.
3. **Encryption**: Each chunk passes through `ISecureChannel.Encrypt`.
4. **Framing**: `ProtocolHandler` wraps the encrypted chunk with the **8-byte** header (Length + CorrelationID + Flags).
5. **Transport**: The relevant `ITransport` (WiFi/BT) transmits the bytes.

### Inbound (Receiving & Dispatching)
1. **Detection**: `ITransport` receives bytes and passes them to `ProtocolHandler`.
2. **Reassembly**: The receiver **must buffer** incoming bytes until a **complete TPack** is available (8-byte header + exactly `Length` bytes of payload) before calling `ParseFrame`. The transport may deliver partial data (e.g. TCP segments, BLE MTU chunks).
3. **De-framing**: `ProtocolHandler` extracts the Correlation ID and payload from the complete TPack.
4. **Dispatching**: The Manager checks the **Routing Map**:
    - **Match Found**: Payload is sent to `ISecureChannel.Decrypt` and then to the registered Handler (e.g., Clipboard handler).
    - **No Match**: Attempt to parse as a new `TransferRequest` JSON (New Handshake).

## 5. Operation examples

### A. BACKUP flow (pull from PC)
**Stream rule:** The approving side (Java) uses the **requester’s CorrelationID (C#)** for sending data too — no new ID is created.
1. **Initiation (C#)**: Python client requests a file. C# generates `CorrelationID: 101` (odd), stores it in the map, and sends on **Wire ID 0**:
   `{ CorrelationID: 101, Status: "REQ", Type: "BACKUP", Payload: "{\"FileName\": \"target.jpg\"}" }`.
2. **Approval (Java)**: Java receives the request, starts the process, **uses C#’s ID** and sends on **Wire ID 0**:
   `{ CorrelationID: 101, Status: "APPROVE", FileSize: 5242880 }`.
3. **Acknowledgment (C#)**: C# responds on **Wire ID 0**:
   `{ CorrelationID: 101, Status: "OK" }`.
4. **Streaming**: Java sends data packets on **Wire ID 101**. C# routes them directly to the Python stream.

### B. CLIPBOARD flow (spontaneous push from phone)
1. **Push (Java)**: Java generates `CorrelationID: 202` (even) and sends on **Wire ID 0**:
   `{ CorrelationID: 202, Status: "PUSH", Type: "CLIPBOARD", FileSize: 150 }`.
2. **Acceptance (C#)**: C# registers a `ClipboardHandler` for ID 202 and responds on **Wire ID 0**:
   `{ CorrelationID: 202, Status: "OK" }`.
3. **Streaming**: Java receives OK and sends clipboard content on **Wire ID 202**.
---

## 6. Cursor Implementation Guidelines
- **Thread Safety**: Use `ConcurrentDictionary` for the Routing Map in C#.
- **Asynchronous**: All methods in Manager and Transport MUST be `async/await` (C#) or `suspend` (Kotlin).
- **Byte Order**: Use `Little Endian` for the Length prefix to ensure cross-platform compatibility.
- **Modular Deployment**: Ensure `IProtocolHandler` and `ISecureChannel` can be swapped for testing purposes (Dependency Injection).
- **TPack reassembly**: When receiving from the transport, buffer bytes until a **complete TPack** is available (8-byte header + `Length` bytes of payload from the header) before calling `ParseFrame`. Do not parse on partial data; the transport may deliver in segments (TCP, BLE MTU, etc.).
- **Stream Buffering**: C# holds an internal buffer per stream so the Python client can consume data at its own rate.
- **Error Handling**: On `Status: REJECT` (rejection reason in `Payload`), or when the ID is not in the map, close resources and report an error to the client. A handshake that receives no response within the configured time throws **TimeoutException**. Multiple concurrent REQ requests are supported — ensure the map and streams handle concurrency.

---
## 7. Resolved Design Notes

- **Handshake:** **IProtocolHandler** owns the full handshake (how data flows). **IConnectionManager** owns which connection type and when (which transport, when to initiate).
- **Control vs data channel:** Signaling uses **CorrelationID = 0**. Agreed stream ID (e.g. 101) is used in the TPack header for data; the Map routes by that ID to the listening client (Python or Android).
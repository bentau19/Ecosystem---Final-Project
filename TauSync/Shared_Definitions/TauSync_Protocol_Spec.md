# 🛰️ TauSync Protocol Specification (v3.0)

**Project Name:** TauSync (Cross-Platform Smart Connectivity)
**Architecture:** 4-Layer Decoupled Communication Stack
**Patterns:** Singleton Transports, Dispatcher/Routing Map, AEAD Security
**Target Platforms:** Windows (C# .NET) & Android (Java/Kotlin)

---

## 1. Logic Layer: `TransferRequest` (Metadata)
The `TransferRequest` object is used **only during the Handshake phase**. It MUST NOT contain the data payload itself to ensure memory-efficient streaming.

| Field | Type | Description |
| :--- | :--- | :--- |
| `MagicBytes` | `uint32` | `0x54415553` ("TAUS") - Protocol identity verification. |
| `RequestId` | `string` | Unique 16-character UTF-8 string used as the Correlation ID. |
| `Type` | `int` | Content type: `0: File`, `1: Clipboard`, `2: Command`. |
| `FileName` | `string?` | Original name of the file (if applicable). |
| `FileSize` | `long` | Total size of the transmission in bytes (for stream allocation). |

---

## 2. Framing Layer: Binary Packet Structure
Every packet sent over a transport MUST follow this binary structure to prevent frame-shift errors:

$$Packet = \underbrace{[Length]}_{4B, \text{ Little Endian}} + \underbrace{[CorrelationID]}_{16B, \text{ UTF-8}} + \underbrace{[EncryptedPayload]}_{NB}$$

---

## 3. Interface Contracts (The Architecture)

### 📡 ITransport (Singleton per Medium)
Manages the physical connection. Implement as a Singleton for each medium (Bluetooth, WiFi).
- `void Connect(string targetId)`: Initializes the connection.
- `void SendRaw(byte[] data)`: Sends raw binary data.
- `bool IsConnected()`: Returns the current connection status.
- **Event:** `OnDataReceived(byte[] data)`: Triggered when raw bytes arrive.

### 🔐 ISecureChannel (AEAD Security)
Handles AES-GCM encryption. Encrypts/Decrypts **only the Payload**.
- `byte[] Encrypt(byte[] plaintext)`: Returns `[IV (12B)] + [Ciphertext + Tag]`.
- `byte[] Decrypt(byte[] ciphertextWithIv)`: Extracts IV and decrypts the content.

### 📜 IProtocolHandler (Framing & Parsing)
Bridges raw bytes and logical entities.
- `byte[] BuildFrame(string correlationId, byte[] payload)`: Constructs the 20-byte header + payload.
- `(string id, byte[] payload) ParseFrame(byte[] rawPacket)`: Deconstructs an incoming packet.
- **Handshake Logic:** Manages sending JSON requests and receiving ACK responses ("OK"/"REJECT").

### 🧠 IConnectionManager (Dispatcher & Routing Map)
The central engine orchestrating all layers.
- **Routing Map:** `Dictionary<string, Action<byte[]>>`: Maps Correlation IDs to specific data handlers.
- `void SmartSend(TransferRequest req, Stream source)`: Selects Transport, performs Handshake, and streams encrypted data.
- `void RegisterHandler(string requestId, Action<byte[]> callback)`: Allows external components (UI/Python) to subscribe to specific streams.

---

## 4. Data Flow (The Pipeline)

### Outbound (Sending Data)
1. **Initiation**: `SmartSend` creates a `TransferRequest` (JSON) and sends it as a Handshake via `ProtocolHandler`.
2. **Waiting**: After receiving "OK", the Manager reads from the `Stream` in 64KB chunks.
3. **Encryption**: Each chunk passes through `ISecureChannel.Encrypt`.
4. **Framing**: `ProtocolHandler` wraps the encrypted chunk with a 20-byte header (Length + original RequestId).
5. **Transport**: The relevant `ITransport` (WiFi/BT) transmits the bytes.

### Inbound (Receiving & Dispatching)
1. **Detection**: `ITransport` receives bytes and passes them to `ProtocolHandler`.
2. **De-framing**: `ProtocolHandler` extracts the Correlation ID.
3. **Dispatching**: The Manager checks the **Routing Map**:
    - **Match Found**: Payload is sent to `ISecureChannel.Decrypt` and then to the registered Handler (e.g., Clipboard handler).
    - **No Match**: Attempt to parse as a new `TransferRequest` JSON (New Handshake).

---

## 5. Cursor Implementation Guidelines
- **Thread Safety**: Use `ConcurrentDictionary` for the Routing Map in C#.
- **Asynchronous**: All methods in Manager and Transport MUST be `async/await` (C#) or `suspend` (Kotlin).
- **Byte Order**: Use `Little Endian` for the Length prefix to ensure cross-platform compatibility.
- **Modular Deployment**: Ensure `IProtocolHandler` and `ISecureChannel` can be swapped for testing purposes (Dependency Injection).
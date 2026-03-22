# TauSync Android SDK

High-level Android library for real-time, bidirectional communication between Android and Windows (or any TauSync-compatible peer) over a single TCP socket.

Built on top of the TauSync protocol (v3.1) — provides multiplexed named channels, automatic framing, and symmetric connect semantics.

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

| Method | Description |
|--------|-------------|
| `listen()` | Start server mode. Blocks until a peer connects. |
| `connectTo(String ip)` | Connect to a server. Blocks until connected. |
| `connect(String word)` | Open a named channel (30s timeout). Blocks until paired. |
| `connect(String word, int timeoutSec)` | Open a channel with custom timeout. |
| `isConnected()` | Returns `true` if the transport layer is active. |
| `newManager()` | Creates another TauSync sharing the same socket. |
| `dispose()` | Releases the underlying ConnectionManager. Idempotent. |

**Role protection**: Once `listen()` is called, `connectTo()` is forbidden (and vice versa). The underlying TCP transport is a process-wide singleton.

### `TauSyncStream` — Bidirectional Channel

#### Read Operations

| Method | Returns | Description |
|--------|---------|-------------|
| `readLine()` | `String` or `null` | Reads until `\n`. Returns without the newline. `null` on EOF. |
| `readLine(int maxLength)` | `String` or `null` | Same, with a custom safety limit. |
| `readExactly(int count)` | `byte[]` | Blocks until exactly N bytes arrive. Throws `EOFException` if stream ends early. |
| `readAll()` | `byte[]` | Reads all remaining data until EOF. |
| `readAll(int chunkSize)` | `byte[]` | Same, with custom buffer size. |
| `getInputStream()` | `InputStream` | Raw InputStream for advanced use. |

#### Write Operations

| Method | Returns | Description |
|--------|---------|-------------|
| `write(byte[] data)` | `int` | Writes raw bytes. Returns count written. |
| `writeString(String text)` | `int` | Encodes as UTF-8 and writes. Returns bytes written. |
| `getOutputStream()` | `OutputStream` | Raw OutputStream for advanced use. |

#### File Transfer

| Method | Returns | Description |
|--------|---------|-------------|
| `writeFile(String path)` | `long` | Streams a file into the channel (64KB chunks). |
| `writeFile(String path, int chunkSize)` | `long` | Same, with custom chunk size. |
| `readToFile(String path, long length)` | `long` | Receives exactly `length` bytes and writes to a file. |
| `readToFile(String path, long length, int chunkSize)` | `long` | Same, with custom chunk size. |

#### Lifecycle

| Method | Description |
|--------|-------------|
| `close()` | Sends FIN to peer, releases the channel ID. Idempotent. |
| `getLocalId()` | Returns the TPack ID assigned to this channel. |

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
- **Permissions**: `android.permission.INTERNET`

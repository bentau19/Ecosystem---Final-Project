# tausync_py - TauSync Python SDK

A socket-like Python wrapper around the TauSync.Lib .NET library.
Hides all CLR initialization, GCHandle memory management, and raw .NET byte
arrays behind a clean two-class API: **`TauSync`** and **`TauSyncStream`**.

## Installation

first go to

```
cd /path/to/Tausync_Windows/
```
then run

```
docker compose up  
```
and then 

```
pip install -e /path/to/windows/
```

Or, if published to PyPI:
```
pip install tausync-py
```

The package auto-discovers `TauSync.Lib.dll` by walking up from its own
directory. If the DLL is elsewhere, pass the path explicitly:

```python
tau = TauSync(dll_path=r"C:\path\to\TauSync.Lib.dll")
```

---

## Quick Start

### Server

```python
from tausync_py import TauSync

tau = TauSync()
tau.listen()                             # wait for a client TCP connection

with tau.connect("main") as stream:      # open channel "main"
    request = stream.read_until(b"\r\n\r\n")
    stream.write(b"HTTP/1.1 200 OK\r\n\r\n")
    stream.write(b"Hello World!")
```

### Client

```python
from tausync_py import TauSync

tau = TauSync()
tau.connect_to("192.168.1.50")           # connect to server

with tau.connect("main") as stream:      # open channel "main"
    stream.write(b"GET / HTTP/1.1\r\n\r\n")
    response = stream.read_all()
    print(response)
```

Both sides call `connect("main")` with the same word - TauSync pairs them
automatically and gives each side a private duplex stream.

---

## Core Concepts

| Concept | Description |
|---------|-------------|
| **Transport** | A single TCP connection (singleton). Call `listen()` or `connect_to()` once per process. |
| **Meeting Word** | A string used to pair two `connect()` calls. Each pair creates an independent duplex channel. |
| **Channel** | A `TauSyncStream` returned by `connect()`. Multiple channels share one TCP connection (multiplexed). |
| **Manager** | A `TauSync` instance. Multiple managers can share the same transport via `new_manager()`. |

---

## API Reference

### `TauSync` - Connection Manager

```python
from tausync_py import TauSync
```

#### Constructor

```python
tau = TauSync(dll_path=None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dll_path` | `str \| None` | `None` | Explicit path to `TauSync.Lib.dll`. Auto-discovered if `None`. |

#### Methods

##### `tau.listen()`

Start listening for an incoming TCP connection (server mode).
Blocks until a remote peer connects. Only needs to be called **once per
process** - the transport is a singleton.

```python
tau = TauSync()
tau.listen()
print("Client connected!")
```

##### `tau.connect_to(ip)`

Connect to a remote TauSync server (client mode).

| Parameter | Type | Description |
|-----------|------|-------------|
| `ip` | `str` | Server IP address (e.g. `"192.168.1.50"`) |

```python
tau = TauSync()
tau.connect_to("192.168.1.50")
```

##### `tau.connect(word, chunk_size=65536) -> TauSyncStream`

Open a named duplex stream via a meeting-word handshake.
Both sides must call `connect(word)` with the **same word** to be paired.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `word` | `str` | *(required)* | Meeting word for the handshake |
| `chunk_size` | `int` | `65536` | Default read buffer size for the returned stream |

Returns a `TauSyncStream`.

```python
stream = tau.connect("upload_channel")
```

##### `tau.new_manager() -> TauSync`

Create another `TauSync` instance sharing the **same singleton socket**.
Useful when you want multiple independent managers for parallel operations.

```python
tau = TauSync()
tau.listen()

mgr1 = tau.new_manager()
mgr2 = tau.new_manager()

stream_a = mgr1.connect("channel_a")
stream_b = mgr2.connect("channel_b")
```

##### `tau.dispose()`

Dispose the underlying .NET `ConnectionManager`. Safe to call multiple times.

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `tau.is_connected` | `bool` | Whether the TCP transport is up |

---

### `TauSyncStream` - Duplex Stream

Returned by `tau.connect()`. Behaves like a Python socket - all methods
accept and return plain Python `bytes`. Supports the `with` statement.

```python
with tau.connect("main") as stream:
    stream.write(b"hello")
    data = stream.read(1024)
```

#### Read Methods

##### `stream.read(n=-1) -> bytes`

Read **up to** *n* bytes (like `socket.recv`). Returns empty `bytes` on EOF.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n` | `int` | `-1` | Max bytes to read. `-1` = default chunk size. |

```python
data = stream.read(4096)
```

##### `stream.read_exactly(n) -> bytes`

Read **exactly** *n* bytes, blocking until all arrive.
Raises `EOFError` if the stream closes before *n* bytes are read.

| Parameter | Type | Description |
|-----------|------|-------------|
| `n` | `int` | Exact number of bytes to read |

```python
header = stream.read_exactly(8)  # read exactly 8 bytes
```

##### `stream.read_all() -> bytes`

Read everything until EOF and return it all. Useful for small responses.

```python
body = stream.read_all()
```

##### `stream.read_line(max_length=1048576) -> bytes`

Read a single line terminated by `\n` (inclusive). Returns empty `bytes`
on EOF. Good for text protocols.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_length` | `int` | `1048576` | Safety limit to prevent unbounded reads |

```python
line = stream.read_line()
print(line.decode())  # "Hello\n"
```

##### `stream.read_until(delimiter) -> bytes`

Read until *delimiter* appears. Returns all bytes **up to and including**
the delimiter. Any overflow bytes (data after the delimiter) are buffered
internally and returned by subsequent `read()` calls - **no data is lost**.

| Parameter | Type | Description |
|-----------|------|-------------|
| `delimiter` | `bytes` | Byte sequence to stop at |

```python
# Read HTTP headers (body data that arrived with headers is preserved)
headers = stream.read_until(b"\r\n\r\n")

# Next read() returns the body bytes - nothing is lost
body_start = stream.read(4096)
```

#### Write Methods

##### `stream.write(data) -> int`

Write raw bytes to the stream. Returns the number of bytes written.

| Parameter | Type | Description |
|-----------|------|-------------|
| `data` | `bytes` | Raw bytes to send |

```python
stream.write(b"GET / HTTP/1.1\r\n\r\n")
```

##### `stream.write_string(text, encoding="utf-8") -> int`

Encode a string and write it. Convenience wrapper around `write()`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | `str` | *(required)* | String to send |
| `encoding` | `str` | `"utf-8"` | Character encoding |

```python
stream.write_string("HTTP/1.1 200 OK\r\n\r\n")
```

##### `stream.flush()`

Flush the write buffer. Call after `write()` / `write_string()` when
you want to ensure data is sent immediately.

```python
stream.write(b"ping")
stream.flush()
```

#### File Transfer Methods

##### `stream.write_file(path, chunk_size=65536) -> int`

Stream a local file into the TauSync channel. Uses a single pinned .NET
buffer - **memory stays constant** regardless of file size (even 1GB+).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str` | *(required)* | Path to the file to send |
| `chunk_size` | `int` | `65536` | Read/write granularity in bytes |

Returns total bytes written.

```python
# Send a file efficiently - works for any size
bytes_sent = stream.write_file("photos/large_image.jpg")
print(f"Sent {bytes_sent} bytes")
```

##### `stream.read_to_file(path, length, chunk_size=65536) -> int`

Read exactly *length* bytes from the stream and save directly to a file.
Streams to disk in chunks - **memory stays constant** regardless of size.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str` | *(required)* | Destination file path (created/overwritten) |
| `length` | `int` | *(required)* | Exact number of bytes to read |
| `chunk_size` | `int` | `65536` | Read granularity in bytes |

Returns total bytes written to disk.

```python
# Save response body to disk (constant memory)
written = stream.read_to_file("download.jpg", content_length)
```

#### Lifecycle

##### `stream.close()`

Dispose the underlying .NET stream. Safe to call multiple times.
Automatically called when using the `with` statement.

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `stream.closed` | `bool` | Whether the stream has been closed |
| `stream.word` | `str` | The meeting-word this stream was opened on |

---

## Patterns & Examples

### Multiple Parallel Channels

```python
import threading
from tausync_py import TauSync

tau = TauSync()
tau.listen()

def handle_channel(word):
    with tau.connect(word) as stream:
        data = stream.read_all()
        print(f"[{word}] received {len(data)} bytes")

words = ["photos", "messages", "files", "status"]
threads = [threading.Thread(target=handle_channel, args=(w,)) for w in words]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

### Multiple Managers on Same Socket

```python
from tausync_py import TauSync

tau = TauSync()
tau.connect_to("192.168.1.50")

# Create 4 independent managers sharing the same TCP connection
managers = [tau.new_manager() for _ in range(4)]

# Each manager can open its own channels
stream_a = managers[0].connect("channel_a")
stream_b = managers[1].connect("channel_b")
```

### HTTP File Server

```python
from tausync_py import TauSync
import os

tau = TauSync()
tau.listen()

while True:
    with tau.connect("http") as stream:
        # Read the request
        request = stream.read_until(b"\r\n\r\n")
        path = request.split(b" ")[1].decode().lstrip("/") or "index.html"

        if os.path.isfile(path):
            size = os.path.getsize(path)
            stream.write_string(
                f"HTTP/1.1 200 OK\r\nContent-Length: {size}\r\n\r\n"
            )
            stream.write_file(path)
        else:
            stream.write(b"HTTP/1.1 404 Not Found\r\n\r\n")
```

### HTTP File Client

```python
from tausync_py import TauSync

tau = TauSync()
tau.connect_to("192.168.1.50")

with tau.connect("http") as stream:
    stream.write_string("GET /photo.jpg HTTP/1.1\r\n\r\n")
    stream.flush()

    # read_until preserves body bytes after the header delimiter
    headers = stream.read_until(b"\r\n\r\n")

    # Parse Content-Length from headers
    content_length = 0
    for line in headers.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            content_length = int(line.split(b":")[1].strip())

    # Stream body directly to disk (constant memory, even for huge files)
    stream.read_to_file("photo.jpg", content_length)
```

### Simple Message Exchange

```python
from tausync_py import TauSync

# Server
tau = TauSync()
tau.listen()
with tau.connect("chat") as stream:
    stream.write_string("Hello from server!\n")
    stream.flush()
    reply = stream.read_line()
    print(f"Got: {reply.decode()}")

# Client (in another process)
tau = TauSync()
tau.connect_to("127.0.0.1")
with tau.connect("chat") as stream:
    msg = stream.read_line()
    print(f"Got: {msg.decode()}")
    stream.write_string("Hello from client!\n")
    stream.flush()
```

---

## Architecture Notes

- **One TCP socket** - `listen()` / `connect_to()` establishes a single TCP
  connection. All channels are multiplexed over it using TauSync's TPack
  framing protocol (8-byte header: 4B length + 3B target ID + 1B flags).

- **Thread-safe** - Each `TauSyncStream` is independent. Multiple threads
  can read/write on different streams simultaneously. The underlying
  `ConnectionContext` routes TPack frames to the correct stream by target ID.

- **Singleton transport** - `TauSync()` creates a new `ConnectionManager`
  but they all share the same transport. Use `new_manager()` to create
  additional managers explicitly.

- **Bulk memory copies** - All Python-to-.NET byte conversions use
  `GCHandle` + `ctypes.memmove` for maximum throughput. No byte-by-byte
  loops.

- **Internal read buffer** - `read_until()` stores any overflow bytes
  (data that arrived after the delimiter) in an internal buffer. Subsequent
  `read()` calls drain this buffer first, so no data is ever lost.

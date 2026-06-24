"""TauSync Python SDK internals.

Handles CLR bootstrap, .NET interop, and exposes ``TauSync`` (connection
manager) and ``TauSyncStream`` (socket-like duplex stream) to callers.

Defensive by design - every public method validates its preconditions and
gives clear error messages instead of leaking raw .NET exceptions.
"""

from __future__ import annotations

import ctypes
import ipaddress
import os
import threading
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
#  CLR bootstrap (runs exactly once per process)
# ---------------------------------------------------------------------------

_clr_ready = False
_clr_lock = threading.Lock()

_Array = None
_Byte = None
_GCHandle = None
_GCHandleType = None
_ConnectionManagerCls = None
_SocketTransportCls = None
_ConnectionContextCls = None
_BleAdvertiserCls = None

_DEFAULT_DLL_RELATIVE = os.path.join(
    "TauSync", "Tausync_Windows", "TauSync.Lib",
    "bin", "Debug", "net8.0", "TauSync.Lib.dll",
)


def _find_dll() -> str:
    """Walk up from this file's directory to locate the DLL automatically."""

    dll_file = Path(__file__).parent / "dll" / "TauSync.Lib.dll"
    #
    # anchor = os.path.dirname(os.path.abspath(__file__))
    # current = anchor
    # for _ in range(10):
    #     candidate = os.path.join(current, _DEFAULT_DLL_RELATIVE)
    #     if os.path.isfile(candidate):
    #         return os.path.abspath(candidate)
    #     parent = os.path.dirname(current)
    #     if parent == current:
    #         break
    #     current = parent
    # raise FileNotFoundError(
    #     f"TauSync.Lib.dll not found. Searched upward from {anchor}. "
    #     "Pass dll_path= explicitly to TauSync() if the DLL is elsewhere."
    # )

    if dll_file.exists():
        return str(dll_file)
    else:
        raise FileNotFoundError(
            f"TauSync.Lib.dll not found.Searched for  {dll_file}. "
            "Pass dll_path= explicitly to TauSync() if the DLL is elsewhere."
        )


def _ensure_clr(dll_path: Optional[str] = None) -> None:
    """Load CoreCLR + TauSync.Lib.dll exactly once (thread-safe)."""
    global _clr_ready, _Array, _Byte, _GCHandle, _GCHandleType, _ConnectionManagerCls
    global _SocketTransportCls, _ConnectionContextCls, _BleAdvertiserCls

    if _clr_ready:
        return

    with _clr_lock:
        if _clr_ready:
            return

        from pythonnet import load as _load_runtime
        try:
            _load_runtime("coreclr")
        except Exception:
            pass

        import clr  # pyright: ignore[reportMissingImports]

        resolved = dll_path or _find_dll()
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"DLL not found at {resolved}")
        clr.AddReference(resolved)

        from System import Array, Byte  # pyright: ignore[reportMissingImports]
        from System.Runtime.InteropServices import GCHandle, GCHandleType  # pyright: ignore[reportMissingImports]
        from TauSync.Implementations.Management import ConnectionManager as _CM  # pyright: ignore[reportMissingImports]
        from TauSync.Implementations.Management import ConnectionContext as _CTX  # pyright: ignore[reportMissingImports]
        from TauSync.Implementations.Transport import SocketTransport as _ST  # pyright: ignore[reportMissingImports]
        from TauSync.Implementations.Discovery import BleAdvertiser as _BLE  # pyright: ignore[reportMissingImports]
        from System import Nullable, Int32, TimeoutException

        _Array = Array
        _Byte = Byte
        _GCHandle = GCHandle
        _GCHandleType = GCHandleType
        _ConnectionManagerCls = _CM
        _ConnectionContextCls = _CTX
        _SocketTransportCls = _ST
        _BleAdvertiserCls = _BLE
        _clr_ready = True


# ---------------------------------------------------------------------------
#  Fast Python <-> .NET byte conversions (GCHandle + memmove)
# ---------------------------------------------------------------------------

def _to_dotnet_bytes(data: bytes):
    """Convert Python ``bytes`` to ``System.Byte[]`` via bulk memory copy."""
    n = len(data)
    arr = _Array.CreateInstance(_Byte, n)
    if n == 0:
        return arr
    handle = _GCHandle.Alloc(arr, _GCHandleType.Pinned)
    try:
        ctypes.memmove(handle.AddrOfPinnedObject().ToInt64(), data, n)
    finally:
        handle.Free()
    return arr


def _from_dotnet_bytes(arr, count: int) -> bytes:
    """Convert first *count* elements of ``System.Byte[]`` to Python ``bytes``."""
    if count <= 0:
        return b""
    handle = _GCHandle.Alloc(arr, _GCHandleType.Pinned)
    try:
        return ctypes.string_at(handle.AddrOfPinnedObject().ToInt64(), count)
    finally:
        handle.Free()


_MIN_CHUNK = 1
_MAX_CHUNK = 16 * 1024 * 1024  # 16 MB


def _validate_chunk_size(value: int, name: str = "chunk_size") -> None:
    if not isinstance(value, int) or value < _MIN_CHUNK or value > _MAX_CHUNK:
        raise ValueError(
            f"{name} must be an integer between {_MIN_CHUNK} and "
            f"{_MAX_CHUNK}, got {value!r}"
        )


# ---------------------------------------------------------------------------
#  TauSyncStream  -  socket-like wrapper around .NET DuplexStream
# ---------------------------------------------------------------------------

class TauSyncStream:
    """Pythonic duplex stream over a TauSync channel.

    Behaves like a mix of ``socket.makefile()`` and ``io.RawIOBase``:
    call ``read``, ``write``, ``read_line``, ``read_all``, etc. with plain
    Python ``bytes`` - all .NET interop is handled internally.

    Args:
        dotnet_stream: The raw .NET ``System.IO.Stream`` returned by
            ``ConnectionManager.Connect(word)``.
        word: The meeting-word this stream was opened on (for logging).
        default_chunk_size: Default buffer size for chunked reads.
    """

    def __init__(
            self,
            dotnet_stream,
            word: str = "",
            default_chunk_size: int = 65536,
    ) -> None:
        if dotnet_stream is None:
            raise ValueError("dotnet_stream must not be None")
        _validate_chunk_size(default_chunk_size, "default_chunk_size")
        self._stream = dotnet_stream
        self._word = word
        self._chunk_size = default_chunk_size
        self._closed = False
        self._close_lock = threading.Lock()
        self._buf = b""  # internal pushback buffer for read_until overflow

    # -- context manager ---------------------------------------------------

    def __enter__(self) -> "TauSyncStream":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # -- read operations ---------------------------------------------------

    def read(self, n: int = -1) -> bytes:
        """Read up to *n* bytes (like ``socket.recv``).

        Returns buffered bytes first (from a previous ``read_until``
        overflow), then reads from the underlying stream.

        Args:
            n: Maximum bytes to read.  ``-1`` means use default chunk size.
                ``0`` returns empty bytes immediately.

        Returns:
            ``bytes`` of length 1..n, or empty ``bytes`` on EOF.

        Raises:
            ValueError: If the stream is closed or *n* is negative
                (other than -1).
        """
        self._check_open()
        if n == 0:
            return b""
        if n < -1:
            raise ValueError(f"read size must be -1, 0, or positive, got {n}")
        size = n if n > 0 else self._chunk_size

        if self._buf:
            chunk = self._buf[:size]
            self._buf = self._buf[size:]
            return chunk

        buf = _Array.CreateInstance(_Byte, size)
        count = self._stream.Read(buf, 0, size)
        return _from_dotnet_bytes(buf, count)

    def read_exactly(self, n: int) -> bytes:
        """Read exactly *n* bytes, blocking until all arrive or EOF.

        Args:
            n: Exact number of bytes required.  Must be >= 0.

        Returns:
            ``bytes`` of length *n*.  ``read_exactly(0)`` returns ``b""``.

        Raises:
            EOFError: If EOF is reached before *n* bytes are read.
            ValueError: If the stream is closed or *n* is negative.
        """
        self._check_open()
        if n < 0:
            raise ValueError(f"read_exactly size must be >= 0, got {n}")
        if n == 0:
            return b""
        parts: list[bytes] = []
        remaining = n
        while remaining > 0:
            chunk = self.read(remaining)
            if not chunk:
                raise EOFError(
                    f"Expected {n} bytes, got {n - remaining} before EOF"
                )
            parts.append(chunk)
            remaining -= len(chunk)
        return b"".join(parts)

    def read_all(self) -> bytes:
        """Read until EOF and return all data.

        Returns:
            All bytes from the stream until the peer closes it.

        Raises:
            ValueError: If the stream is closed.
        """
        self._check_open()
        parts: list[bytes] = []
        while True:
            chunk = self.read(self._chunk_size)
            if not chunk:
                break
            parts.append(chunk)
        return b"".join(parts)

    def read_line(self, max_length: int = 1_048_576) -> bytes:
        r"""Read a single line terminated by ``\n`` (inclusive).

        Consumes the internal buffer first, then reads byte-by-byte from
        the stream.  Suitable for text protocols, not bulk data.
        Returns empty ``bytes`` on EOF.

        Args:
            max_length: Safety limit to prevent unbounded reads.
                Must be >= 1.

        Returns:
            A ``bytes`` line including the trailing ``\n``, or partial
            data if EOF is reached first.

        Raises:
            ValueError: If the stream is closed or *max_length* < 1.
        """
        self._check_open()
        if max_length < 1:
            raise ValueError(f"max_length must be >= 1, got {max_length}")

        if self._buf:
            idx = self._buf.find(b"\n")
            if idx != -1:
                line = self._buf[:idx + 1]
                self._buf = self._buf[idx + 1:]
                return line

        buf = bytearray(self._buf)
        self._buf = b""
        one = _Array.CreateInstance(_Byte, 1)
        while len(buf) < max_length:
            n = self._stream.Read(one, 0, 1)
            if n <= 0:
                break
            b = one[0]
            buf.append(b)
            if b == 0x0A:
                break
        return bytes(buf)

    def read_until(self, delimiter: bytes) -> bytes:
        """Read until *delimiter* appears in the accumulated data.

        The returned data **includes** the delimiter.  Any bytes that
        arrived *after* the delimiter are kept in an internal buffer and
        returned by subsequent ``read()`` / ``read_exactly()`` calls, so
        no data is ever lost.

        Args:
            delimiter: Non-empty byte sequence to stop at
                (e.g. ``b"\\r\\n\\r\\n"``).

        Returns:
            All bytes up to and including the delimiter.
            On EOF without finding the delimiter, returns whatever was read.

        Raises:
            ValueError: If the stream is closed or *delimiter* is empty.
        """
        self._check_open()
        if not delimiter:
            raise ValueError("delimiter must not be empty")
        data = self._buf
        self._buf = b""
        while True:
            idx = data.find(delimiter)
            if idx != -1:
                split = idx + len(delimiter)
                self._buf = data[split:]
                return data[:split]
            chunk = self._raw_read(4096)
            if not chunk:
                return data
            data += chunk

    # -- write operations --------------------------------------------------

    def write(self, data: bytes) -> int:
        """Write *data* to the stream.

        Args:
            data: Raw bytes to send.

        Returns:
            Number of bytes written (always ``len(data)``).

        Raises:
            TypeError: If *data* is not ``bytes`` or ``bytearray``.
            ValueError: If the stream is closed.
        """
        self._check_open()
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError(
                f"write() argument must be bytes-like, not {type(data).__name__}"
            )
        if not data:
            return 0
        raw = bytes(data)
        arr = _to_dotnet_bytes(raw)
        # Raw byte write carries no file/string semantics — let the library route by size
        # (small → Bluetooth, large → Wi-Fi) in hybrid mode.
        self._stream.Write(arr, 0, len(raw))
        return len(raw)

    def _write_over(self, data: bytes, prefer_wifi: bool) -> int:
        """Write *data* over an explicitly chosen transport (hybrid mode).

        ``prefer_wifi`` True routes over Wi-Fi, False over Bluetooth.  This lets each
        high-level method pick the link by its own semantics (``write_file`` → Wi-Fi,
        ``write_string`` → Bluetooth) rather than by payload size.  In single-transport
        mode (Wi-Fi-only or Bluetooth-only) the flag is ignored.
        """
        self._check_open()
        if not data:
            return 0
        raw = bytes(data)
        arr = _to_dotnet_bytes(raw)
        self._stream.Write(arr, 0, len(raw), prefer_wifi)
        return len(raw)

    def write_string(self, text: str, encoding: str = "utf-8") -> int:
        """Encode *text* and write to the stream.

        Strings are control/text traffic and are always sent over Bluetooth in hybrid
        mode (never over Wi-Fi), regardless of length.

        Args:
            text: String to send.
            encoding: Character encoding (default ``utf-8``).

        Returns:
            Number of bytes written.

        Raises:
            TypeError: If *text* is not a ``str``.
            ValueError: If the stream is closed.
        """
        if not isinstance(text, str):
            raise TypeError(
                f"write_string() argument must be str, not {type(text).__name__}"
            )
        return self._write_over(text.encode(encoding), prefer_wifi=False)

    def flush(self) -> None:
        """Flush the underlying .NET stream's write buffer.

        Raises:
            ValueError: If the stream is closed.
        """
        self._check_open()
        self._stream.Flush()

    # -- file transfer helpers ---------------------------------------------

    def write_file(self, path: str, chunk_size: int = 262144) -> int:
        """Stream a local file into the TauSync channel.

        Uses a single pinned .NET buffer for the whole transfer so memory
        stays constant regardless of file size.

        A file is bulk data and is always sent over the high-throughput Wi-Fi
        link in hybrid Bluetooth+Wi-Fi mode (each chunk is flagged for Wi-Fi
        explicitly, so routing no longer depends on ``chunk_size``).  In
        single-transport mode the one available link is used.

        Args:
            path: Path to the file to send.
            chunk_size: Read/write granularity in bytes (1 .. 16 MB).

        Returns:
            Total bytes written.

        Raises:
            FileNotFoundError: If *path* does not exist.
            ValueError: If the stream is closed or *chunk_size* is invalid.
        """
        self._check_open()
        _validate_chunk_size(chunk_size, "chunk_size")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path}")
        buf = _Array.CreateInstance(_Byte, chunk_size)
        handle = _GCHandle.Alloc(buf, _GCHandleType.Pinned)
        buf_addr = handle.AddrOfPinnedObject().ToInt64()
        total = 0
        try:
            with open(path, "rb") as f:
                while True:
                    piece = f.read(chunk_size)
                    if not piece:
                        break
                    ctypes.memmove(buf_addr, piece, len(piece))
                    self._stream.Write(buf, 0, len(piece), True)  # files → Wi-Fi
                    total += len(piece)
            self._stream.Flush()
        finally:
            handle.Free()
        return total

    def read_to_file(
            self,
            path: str,
            length: int,
            chunk_size: int = 65536,
    ) -> int:
        """Read exactly *length* bytes from the stream and save to a file.

        Streams directly to disk in *chunk_size* pieces so memory usage is
        constant regardless of file size.

        Args:
            path: Destination file path (created/overwritten).
            length: Exact number of bytes to read.  Must be >= 0.
            chunk_size: Read granularity in bytes (1 .. 16 MB).

        Returns:
            Total bytes written to disk.

        Raises:
            ValueError: If the stream is closed, *length* < 0, or
                *chunk_size* is invalid.
        """
        self._check_open()
        if length < 0:
            raise ValueError(f"length must be >= 0, got {length}")
        _validate_chunk_size(chunk_size, "chunk_size")
        if length == 0:
            with open(path, "wb"):
                pass
            return 0
        written = 0
        with open(path, "wb") as f:
            while written < length:
                remaining = length - written
                chunk = self.read(min(remaining, chunk_size))
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
        return written

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Dispose the underlying .NET stream.

        Thread-safe.  Safe to call multiple times.
        """
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        try:
            self._stream.Dispose()
        except Exception:
            pass

    @property
    def closed(self) -> bool:
        """Whether the stream has been closed."""
        return self._closed

    @property
    def word(self) -> str:
        """The meeting-word this stream was opened on."""
        return self._word

    # -- internal ----------------------------------------------------------

    def _raw_read(self, n: int) -> bytes:
        """Read directly from the .NET stream, bypassing the internal buffer."""
        buf = _Array.CreateInstance(_Byte, n)
        count = self._stream.Read(buf, 0, n)
        return _from_dotnet_bytes(buf, count)

    def _check_open(self) -> None:
        if self._closed:
            raise ValueError("I/O operation on closed TauSyncStream")

    def __repr__(self) -> str:
        state = "closed" if self._closed else "open"
        return f"<TauSyncStream word={self._word!r} {state}>"


# ---------------------------------------------------------------------------
#  TauSync  -  main entry point (replaces ConnectionManager boilerplate)
# ---------------------------------------------------------------------------

_ROLE_NONE = "none"
_ROLE_SERVER = "server"
_ROLE_CLIENT = "client"


class TauSync:
    """High-level TauSync connection manager.

    Wraps CLR initialization, DLL loading, and ``ConnectionManager`` so
    callers only deal with plain Python objects.

    The transport is a process-wide singleton: only ONE call to ``listen()``
    or ``connect_to()`` can succeed per process.  Attempting to switch roles
    or reconnect to a different address raises ``RuntimeError``.

    Args:
        dll_path: Explicit path to ``TauSync.Lib.dll``.  If ``None``, the
            DLL is discovered automatically by walking up from this package.

    Example::

        tau = TauSync()
        tau.listen()                       # server mode
        stream = tau.connect("main")       # open a named channel
        data = stream.read(1024)           # plain Python bytes
        stream.write(b"hello")
        stream.close()
    """

    _global_role: str = _ROLE_NONE
    _global_role_lock = threading.Lock()
    _global_target: Optional[str] = None

    def __init__(self, dll_path: Optional[str] = None) -> None:
        _ensure_clr(dll_path)
        self._manager = _ConnectionManagerCls(False)
        self._disposed = False
        self._ble_advertiser = None
        self._approve_delegate = None  # keeps the .NET approval delegate alive (GC guard)

    def get_peer_waiting_words(self) -> list[str]:
        """Get a snapshot of the peer's pending discovery words.

        These are the words that the peer has fired REQ frames for but
        has not yet paired with a local word.  This is useful for
        debugging and testing to see what the peer is waiting on.

        Returns:
            A list of strings representing the peer's waiting words.

        Raises:
            RuntimeError: If the transport is not connected or this manager
                has been disposed.
        """
        self._check_not_disposed()
        # if TauSync._global_role == _ROLE_NONE:
        #     raise RuntimeError(
        #         "Cannot GetPeerWaitingWords() - transport is not established.  "
        #         "Call listen() or connect_to() first."
        #     )
        return list(self._manager.GetPeerWaitingWords())

    # -- transport ---------------------------------------------------------

    def listen(self, timeout_seconds: int | None = None) -> None:
        """Start listening for an incoming TCP connection (server mode).

        Blocks until a remote peer connects.  Only needs to be called once
        per process - the underlying transport is a singleton.

        Args:
            timeout_seconds: Max seconds to wait for a client.
                ``None`` (default) waits forever.

        Raises:
            TimeoutError: If no client connected within *timeout_seconds*.
            RuntimeError: If the transport was already established in
                client mode, or if already listening.
        """
        from System import TimeoutException

        self._check_not_disposed()
        with TauSync._global_role_lock:
            if TauSync._global_role == _ROLE_CLIENT:
                raise RuntimeError(
                    "Cannot listen() - transport is already connected in "
                    f"client mode (to {TauSync._global_target!r}). "
                    "The transport is a singleton; you cannot switch roles."
                )
            if TauSync._global_role == _ROLE_SERVER:
                return  # already listening, idempotent
            TauSync._global_role = _ROLE_SERVER
            TauSync._global_target = "0.0.0.0 (listening)"
        try:
            self._manager.ConnectTransport("", timeout_seconds).GetAwaiter().GetResult()
        except TimeoutException as exc:
            with TauSync._global_role_lock:
                TauSync._global_role = _ROLE_NONE
                TauSync._global_target = None
            raise TimeoutError(str(exc))
        except Exception:
            with TauSync._global_role_lock:
                TauSync._global_role = _ROLE_NONE
                TauSync._global_target = None

            raise

    def connect_to(self, ip: str, timeout_seconds: int | None = None) -> None:
        """Connect to a remote TauSync server, or listen if *ip* is empty.

        Passing an empty string (``""``) is equivalent to calling
        ``listen()`` - the transport enters server mode and waits for an
        incoming connection.

        Args:
            ip: Server IP address (e.g. ``"192.168.1.50"``), or ``""``
                to listen (server mode).
            timeout_seconds: Max seconds for the connection attempt.
                ``None`` (default) retries forever.

        Raises:
            TimeoutError: If the connection was not established within
                *timeout_seconds*.
            ValueError: If *ip* is non-empty but not a valid IPv4 address.
            RuntimeError: If the transport was already established in
                the opposite role, or already connected to a different
                address.
        """

        from System import TimeoutException

        self._check_not_disposed()
        ip = ip.strip() if ip else ""

        # Empty string = server mode (documented fallback). Validate the address
        # only for client mode — validating first broke the fallback by raising
        # AddressValueError before listen() could ever run.
        if not ip:
            self.listen(timeout_seconds)
            return

        ipaddress.IPv4Address(ip)

        with TauSync._global_role_lock:
            if TauSync._global_role == _ROLE_SERVER:
                raise RuntimeError(
                    "Cannot connect_to() - transport is already in server "
                    "(listen) mode.  The transport is a singleton; you "
                    "cannot switch roles."
                )
            if TauSync._global_role == _ROLE_CLIENT:
                if TauSync._global_target != ip:
                    raise RuntimeError(
                        f"Cannot connect_to({ip!r}) - transport is already "
                        f"connected to {TauSync._global_target!r}.  The "
                        "transport is a singleton; you cannot reconnect to "
                        "a different address."
                    )
                return  # already connected to the same ip, idempotent
            TauSync._global_role = _ROLE_CLIENT
            TauSync._global_target = ip
        try:
            self._manager.ConnectTransport(ip, timeout_seconds).GetAwaiter().GetResult()
        except TimeoutException as exc:
            with TauSync._global_role_lock:
                TauSync._global_role = _ROLE_NONE
                TauSync._global_target = None
            raise TimeoutError(str(exc))
        except Exception:
            with TauSync._global_role_lock:
                TauSync._global_role = _ROLE_NONE
                TauSync._global_target = None
            raise

    def connect_hybrid(
        self,
        timeout_seconds: int | None = None,
        device_name: str | None = None,
        on_approve=None,
    ) -> None:
        """Start a hybrid Bluetooth + Wi-Fi session as the server (Windows side).

        Windows is always the Bluetooth RFCOMM **server** (and the Wi-Fi server). This
        starts the RFCOMM listener, waits for the Android client to connect, and runs the
        BT_MAGIC handshake. Bluetooth is the always-on primary link; Wi-Fi is brought up
        lazily only when a large payload needs it.

        During the handshake the peer's Wi-Fi IP is exchanged over Bluetooth, so neither
        side needs the address typed in — read it back from :pyattr:`peer_wifi_ip`.

        Args:
            timeout_seconds: Max seconds to wait for the Bluetooth client to connect.
                ``None`` (default) waits forever.
            device_name: Name shown to the phone in its "connect to this PC?" dialog
                during first-time BLE discovery. ``None``/blank uses the Windows computer
                name. Truncated to fit the BLE advertisement (~14 bytes).
            on_approve: Optional ``callable(phone_name: str | None) -> bool`` run when a
                phone connects, before the session completes. Return ``True`` to accept or
                ``False`` to decline (the phone is told and aborts). ``None`` accepts all.
                Called on a background thread — marshal any UI to your main thread.

        Raises:
            TimeoutError: If no Bluetooth client connected within *timeout_seconds*.
            RuntimeError: If the transport was already established in another role/mode.
        """
        from System import TimeoutException

        self._check_not_disposed()
        with TauSync._global_role_lock:
            if TauSync._global_role == _ROLE_CLIENT:
                raise RuntimeError(
                    "Cannot connect_hybrid() - transport is already connected in "
                    f"client mode (to {TauSync._global_target!r}). "
                    "The transport is a singleton; you cannot switch roles."
                )
            if TauSync._global_role == _ROLE_SERVER:
                return  # already serving, idempotent
            TauSync._global_role = _ROLE_SERVER
            TauSync._global_target = "bt:0.0.0.0 (listening)"

        try:
            # Advertise a BLE beacon (UUID only) so a first-time Android client can discover this PC
            # without anyone typing a MAC. It runs during the listen window and is stopped once a
            # client connects. No-op on hardware without BLE peripheral support — the phone then
            # falls back to manual MAC entry.
            self._ble_advertiser = _BleAdvertiserCls(device_name)
            try:
                self._ble_advertiser.StartAsync().GetAwaiter().GetResult()
            except Exception:
                pass  # BLE peripheral unsupported — manual MAC entry still works

            # Bluetooth is the primary (RFCOMM server) link; the singleton's Wi-Fi
            # SocketTransport is the lazy secondary. The hybrid ConnectionManager starts the
            # BT listener itself and runs the BT_MAGIC handshake (where the peer's Wi-Fi IP
            # is discovered).
            self._manager = _ConnectionManagerCls()
            if on_approve is not None:
                from System import Func, String, Boolean
                # Keep a reference so the delegate is not garbage-collected while .NET holds it.
                self._approve_delegate = Func[String, Boolean](on_approve)
                self._manager.SetBtApprovalCallback(self._approve_delegate)
            self._manager.ConnectTransport("", timeout_seconds).GetAwaiter().GetResult()
            self._stop_ble_advertiser()  # client connected — no need to keep advertising
        except TimeoutException as exc:
            self._stop_ble_advertiser()
            with TauSync._global_role_lock:
                TauSync._global_role = _ROLE_NONE
                TauSync._global_target = None
            raise TimeoutError(str(exc))
        except Exception:
            self._stop_ble_advertiser()
            with TauSync._global_role_lock:
                TauSync._global_role = _ROLE_NONE
                TauSync._global_target = None
            raise

    def _stop_ble_advertiser(self) -> None:
        """Stop BLE advertising if it is running. Safe to call repeatedly / on non-hybrid instances."""
        advertiser = getattr(self, "_ble_advertiser", None)
        if advertiser is not None:
            try:
                advertiser.Stop()
            except Exception:
                pass
            self._ble_advertiser = None

    @property
    def peer_wifi_ip(self) -> Optional[str]:
        """The peer's Wi-Fi IPv4 address discovered over Bluetooth, or ``None``.

        Populated during the hybrid BT_MAGIC handshake (see :pymeth:`connect_hybrid`), so
        the address is available without anyone typing it in.
        """
        try:
            return _ConnectionContextCls.Instance.GetPeerWifiHost()
        except Exception:
            return None

    @property
    def wifi_active(self) -> bool:
        """Whether the lazy Wi-Fi link is currently up (hybrid mode).

        Flips to true after the first large payload brings Wi-Fi online and back to false
        after the idle teardown, so tests can assert size-based routing.
        """
        try:
            wifi = _ConnectionContextCls.Instance.GetWifiTransportAsSocket()
            return bool(wifi is not None and wifi.IsConnected())
        except Exception:
            return False

    @property
    def is_connected(self) -> bool:
        """Whether the underlying TCP transport is up."""
        if self._disposed:
            return False
        try:
            if not self._manager.IsConnected():
                return False
        except Exception:
            return False
        return TauSync._global_role != _ROLE_NONE

    @property
    def role(self) -> str:
        """Current transport role: ``"none"``, ``"server"``, or ``"client"``."""
        return TauSync._global_role

    # -- channels ----------------------------------------------------------

    def connect(
            self,
            word: str,
            chunk_size: int = 65536,
            timeout_seconds: int | None = 60,
    ) -> TauSyncStream:
        """Open a named duplex stream (meeting-word handshake).

        Both sides must call ``connect(word)`` with the same word; they are
        paired automatically and each gets a private ``TauSyncStream``.

        Args:
            word: Meeting word for the handshake (e.g. ``"main"``).
                Must be a non-empty, non-blank string.
            chunk_size: Default read buffer size for the returned stream
                (1 .. 16 MB).
            timeout_seconds: Max seconds to wait for the peer to call
                ``connect(word)`` too.  NOTE: unlike ``listen``/``connect_to``,
                ``None`` here does NOT mean "wait forever" — it falls back to
                the library default handshake timeout (30 s, CoreConfig
                ``HandshakeTimeoutSeconds``).

        Returns:
            A ``TauSyncStream`` wrapping the paired duplex channel.

        Raises:
            TimeoutError: If the handshake did not complete within
                *timeout_seconds*.
            RuntimeError: If the transport is not connected, the manager has
                been disposed, or another ``connect()`` with the same word is
                still in flight (concurrent same-word guard — wait for it to
                resolve or use a distinct word).
            ValueError: If *word* is empty/blank or *chunk_size* is invalid.
        """
        from System import TimeoutException

        self._check_not_disposed()
        if TauSync._global_role == _ROLE_NONE:
            raise RuntimeError(
                "Cannot connect() - transport is not established.  "
                "Call listen() or connect_to() first."
            )
        if not isinstance(word, str) or not word.strip():
            raise ValueError("word must be a non-empty, non-blank string")
        _validate_chunk_size(chunk_size, "chunk_size")
        try:
            dotnet_stream = self._manager.Connect(word, timeout_seconds).GetAwaiter().GetResult()
            return TauSyncStream(dotnet_stream, word=word, default_chunk_size=chunk_size)
        except TimeoutException as exc:
            raise TimeoutError(str(exc))
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to word {word!r}: {exc}") from exc

    # -- lifecycle ---------------------------------------------------------

    def dispose(self) -> None:
        """Dispose the underlying ``ConnectionManager``.

        After this call, ``connect()``, ``listen()``, and ``connect_to()``
        will raise ``RuntimeError``.  Safe to call multiple times.
        """
        if self._disposed:
            return
        self._disposed = True
        self._stop_ble_advertiser()
        try:
            self._manager.Dispose()
            TauSync._global_role = _ROLE_NONE
        except Exception:
            pass

    def disconnect(self) -> None:
        """Close the TCP transport and reset the process-wide role to ``none``.

        After this call ``is_connected`` returns ``False`` and ``listen()`` /
        ``connect_to()`` may be called again on the same instance.

        Safe to call on an already-disconnected transport (no-op).

        Raises:
            RuntimeError: If this instance has been disposed.
        """
        self._check_not_disposed()
        self._stop_ble_advertiser()
        if not self.is_connected:
            return
        self._manager.Disconnect()
        with TauSync._global_role_lock:
            TauSync._global_role = _ROLE_NONE
            TauSync._global_target = None

    def new_manager(self) -> "TauSync":
        """Create another ``TauSync`` instance sharing the same singleton socket.

        Useful for opening channels from multiple independent managers
        on the same transport.

        Returns:
            A new ``TauSync`` instance whose transport is already connected.

        Raises:
            RuntimeError: If this manager has been disposed or the
                transport is not yet established.
        """
        self._check_not_disposed()
        if TauSync._global_role == _ROLE_NONE:
            raise RuntimeError(
                "Cannot new_manager() - transport is not established.  "
                "Call listen() or connect_to() first."
            )
        ts = TauSync.__new__(TauSync)
        ts._manager = _ConnectionManagerCls(False)
        ts._disposed = False
        return ts

    # -- internal ----------------------------------------------------------

    def _check_not_disposed(self) -> None:
        if self._disposed:
            raise RuntimeError(
                "This TauSync instance has been disposed.  "
                "Create a new TauSync() to continue."
            )

    def __repr__(self) -> str:
        if self._disposed:
            return "<TauSync disposed>"
        return f"<TauSync role={TauSync._global_role} target={TauSync._global_target!r}>"

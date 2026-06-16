import json
import struct
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from PySide6.QtCore import QObject, Signal

from domain.enums.virtual_drive_channels import VirtualDriveChannels
from native import Server
from services.connectivity import ConnectivityService


class VirtualDriveService(QObject):
    r"""Pipe server that bridges VirtualDrive.exe WinFsp ops to Android via TauSync.

    SyncDose.exe listens on ``\\\\.\pipe\SyncDoseVDrive`` (byte-stream mode).
    VirtualDrive.exe connects and sends framed requests; this service dispatches
    each ``"op"`` to the appropriate TauSync channel and writes a framed response.

    Read and write sessions each use a unique UUID-suffixed TauSync channel to
    prevent collisions when multiple files are transferred simultaneously:

    - ``virtual_drive_read_{uuid}``  — data channel per read request
    - ``virtual_drive_write_{uuid}`` — persistent data channel per write session

    The negotiation for both happens on the base meeting word
    (``virtual_drive_read`` / ``virtual_drive_write``); Android learns the UUID
    from the JSON payload and opens the unique data channel.

    Lifecycle is managed externally: ``start()`` on ``device_connected``,
    ``stop()`` on ``device_disconnected``.

    Signals:
        drive_error (str): Emitted when a fatal pipe-level error occurs.
    """

    drive_error: Signal = Signal(str)

    # Pipe name SyncDose exposes for VirtualDrive.exe.
    _PIPE_NAME: str = r'\\.\pipe\SyncDoseVDrive'

    # Seconds a cached stat/list entry stays valid before a fresh round-trip is
    # forced. Bounds how stale phone-side changes can appear; mutations made
    # through this service invalidate their paths immediately regardless.
    _CACHE_TTL_SECONDS: float = 5.0

    # Max concurrent VirtualDrive.exe connections served in parallel. Must be
    # >= the C++ client's pipe-pool size so every pooled connection can be
    # accepted and handled on its own thread. The +1 worker runs the accept loop.
    _MAX_CONNECTIONS: int = 8

    def __init__(
            self,
            connectivity: ConnectivityService,
            parent: QObject | None = None,
    ) -> None:
        """Initialize with the shared connectivity service.

        Args:
            connectivity: Application-level connectivity service; ``tau`` is
                read per-call so reconnects are handled transparently.
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._connectivity: ConnectivityService = connectivity
        self._is_running: threading.Event = threading.Event()
        self._executor: ThreadPoolExecutor | None = None
        self._lifecycle_lock: threading.Lock = threading.Lock()
        # Active write sessions: virtual path → open TauSync stream. Now that
        # connections are served concurrently, mutations are guarded by a lock.
        self._write_sessions_lock: threading.Lock = threading.Lock()
        self._write_sessions: dict[str, Any] = {}
        # Short-TTL metadata caches: virtual path → (response_dict, expiry_monotonic).
        # _stat_cache answers `stat`; _list_cache answers `list`. Both cut the
        # repeated round-trips WinFsp issues while browsing (root-stat storm,
        # per-entry stats). Guarded by _cache_lock for safety.
        self._cache_lock: threading.Lock = threading.Lock()
        self._stat_cache: dict[str, tuple[dict, float]] = {}
        self._list_cache: dict[str, tuple[dict, float]] = {}

    # ── Public lifecycle ───────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the pipe server on a background thread."""
        threading.Thread(target=self._start, daemon=True).start()

    def stop(self) -> None:
        """Shut down the pipe server, waiting for in-flight ops to finish."""
        threading.Thread(target=self._stop, daemon=True).start()

    # ── Private lifecycle ──────────────────────────────────────────────────────

    def _start(self) -> None:
        # Guard against double-start.
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._is_running.set()
            # One worker for the accept loop + one per concurrent connection.
            self._executor = ThreadPoolExecutor(max_workers=self._MAX_CONNECTIONS + 1)
            self._executor.submit(self._serve_loop)

    def _stop(self) -> None:
        # _stop uses a bare thread (not executor) so it can call shutdown(wait=True)
        # without deadlocking on the same executor it is trying to stop.
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
            self._executor.shutdown(wait=True)

    # ── Pipe server loop ───────────────────────────────────────────────────────

    def _serve_loop(self) -> None:
        # Accept loop: each iteration creates a fresh pipe instance (the pipe is
        # PIPE_UNLIMITED_INSTANCES), waits for a client, then hands the connected
        # instance to a worker thread. This lets the C++ client's pool of N
        # connections be served concurrently — N ops in flight at once.
        while self._is_running.is_set():
            pipe = Server(65536, 65536, self._PIPE_NAME, byte_stream=True)
            try:
                pipe.wait_for_client(timeout=timedelta(seconds=3))
            except TimeoutError:
                # No client this round — drop this instance and create a new one.
                pipe.close()
                continue
            except Exception as exc:
                self.drive_error.emit(str(exc))
                pipe.close()
                continue
            # Connection established — serve it on its own worker thread so the
            # accept loop is free to take the next pooled connection immediately.
            self._executor.submit(self._serve_connection, pipe)

    def _serve_connection(self, pipe: Any) -> None:
        # Serve one connected VirtualDrive.exe pipe instance to completion, then
        # tear it down. Runs on its own worker thread.
        try:
            self._handle_connection(pipe)
        except Exception as exc:
            self.drive_error.emit(str(exc))
        finally:
            pipe.disconnect()
            pipe.close()

    def _handle_connection(self, pipe: Any) -> None:
        # Serve one connected VirtualDrive.exe session. Requests on a single
        # connection are sequential (request→response paired on the wire);
        # concurrency comes from multiple connections served in parallel.
        while self._is_running.is_set():
            try:
                req, payload, = self._read_frame(pipe)
                print(f"request: req={req} payload={payload}")
            except Exception:
                # Pipe broken or client disconnected — exit the session loop.
                break
            try:
                resp, resp_payload, = self._dispatch(req, payload)
                print(f"respond: resp= {resp} resp_payload={resp_payload}")
            except Exception as exc:
                # Surface the failure: a swallowed op error reaches VirtualDrive.exe
                # as {"ok": false} with no indication of what actually went wrong.
                self.drive_error.emit(f"op {req.get('op')!r} failed: {exc}")
                resp, resp_payload, = {"ok": False, "error": str(exc)}, b''
            self._write_frame(pipe, resp, resp_payload)

    # ── Frame helpers (mirror of Protocol.cpp) ─────────────────────────────────

    @staticmethod
    def _read_frame(pipe: Any) -> tuple[dict, bytes]:
        """Read one framed message from the pipe.

        Frame layout (matches ``Protocol.h``):
            [4B LE jsonLen][JSON bytes][4B LE payloadLen][payload bytes]

        Both length prefixes are read in a single ``read_exact(8)`` call; the
        write side always sends the whole frame atomically so all bytes are
        already in the kernel buffer by the time the first byte is readable.
        """
        header = pipe.read_exact(8)
        json_len, pay_len = struct.unpack_from('<II', header)
        body = pipe.read_exact(json_len + pay_len) if (json_len + pay_len) else b''
        return json.loads(body[:json_len]), body[json_len:]

    @staticmethod
    def _write_frame(pipe: Any, resp: dict, payload: bytes = b'') -> None:
        """Write one framed response to the pipe.

        Frame layout: ``[4B JSON_len][4B payload_len][JSON bytes][payload bytes]``
        Both lengths are front-loaded so the reader needs only one 8-byte read
        for the header instead of two separate 4-byte reads.
        """
        j = json.dumps(resp).encode('utf-8')
        pipe.write(struct.pack('<II', len(j), len(payload)) + j + payload)

    # ── Dispatch ───────────────────────────────────────────────────────────────

    def _dispatch(self, req: dict, payload: bytes) -> tuple[dict, bytes]:
        """Route a request to the appropriate op handler.

        Args:
            req: Parsed JSON from the pipe frame.
            payload: Raw binary payload (non-empty only for ``write`` ops).

        Returns:
            ``(response_dict, response_payload)`` — response_payload is empty
            for all ops except ``read``.
        """
        op = req.get("op", "")
        handlers = {
            "list": self._op_list,
            "stat": self._op_stat,
            "read": self._op_read,
            "write_open": self._op_write_open,
            "write": self._op_write,
            "write_close": self._op_write_close,
            "create": self._op_create,
            "delete": self._op_delete,
            "rename": self._op_rename,
            "truncate": self._op_truncate,
        }
        handler = handlers.get(op)
        if handler is None:
            return {"ok": False, "error": f"unknown op: {op}"}, b''
        return handler(req, payload)

    # ── Metadata cache helpers ─────────────────────────────────────────────────

    @staticmethod
    def _parent_path(path: str) -> str | None:
        # Parent virtual path, or None for the root.
        if path == "/" or not path:
            return None
        idx = path.rfind("/")
        return path[:idx] if idx > 0 else "/"

    @staticmethod
    def _child_path(parent: str, name: str) -> str:
        # Join a parent dir and a child entry name into a normalized virtual path.
        return f"/{name}" if parent == "/" else f"{parent}/{name}"

    def _invalidate(self, *paths: str) -> None:
        # Drop cached stat/list entries for the given paths and their parents,
        # since a mutation changes both the path itself and its parent's listing.
        with self._cache_lock:
            for path in paths:
                self._stat_cache.pop(path, None)
                self._list_cache.pop(path, None)
                parent = self._parent_path(path)
                if parent is not None:
                    self._stat_cache.pop(parent, None)
                    self._list_cache.pop(parent, None)

    # ── One-shot ops (fixed meeting word) ──────────────────────────────────────

    def _op_list(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """List directory entries at ``req["path"]``.

        Cached for ``_CACHE_TTL_SECONDS``. A successful listing also seeds the
        stat cache for every child so the per-entry ``stat`` storm WinFsp issues
        right after a directory open is served locally without round-trips.
        """
        path = req["path"]
        now = time.monotonic()
        with self._cache_lock:
            hit = self._list_cache.get(path)
            if hit is not None and hit[1] > now:
                return hit[0], b''

        tau = self._connectivity.tau
        with tau.connect(
                VirtualDriveChannels.VIRTUAL_DRIVE_LIST.value, timeout_seconds=30
        ) as s:
            s.write_string(json.dumps({"path": path}) + "\n")
            resp = json.loads(s.read_all().decode())

        if resp.get("ok"):
            expiry = time.monotonic() + self._CACHE_TTL_SECONDS
            with self._cache_lock:
                self._list_cache[path] = (resp, expiry)
                # Seed child stats from the listing.
                for entry in resp.get("entries", []):
                    name = entry.get("name")
                    if not name:
                        continue
                    child = self._child_path(path, name)
                    self._stat_cache[child] = ({**entry, "ok": True}, expiry)
        return resp, b''

    def _op_stat(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Return metadata for the file or directory at ``req["path"]``.

        Cached for ``_CACHE_TTL_SECONDS`` to absorb the repeated ``stat('/')``
        refreshes and per-entry probes WinFsp issues while browsing.
        """
        path = req["path"]
        now = time.monotonic()
        with self._cache_lock:
            hit = self._stat_cache.get(path)
            if hit is not None and hit[1] > now:
                return hit[0], b''

        tau = self._connectivity.tau
        with tau.connect(VirtualDriveChannels.VIRTUAL_DRIVE_STAT.value, timeout_seconds=30) as s:
            s.write_string(json.dumps({"path": path}) + "\n")
            resp = json.loads(s.read_all().decode())

        if resp.get("ok"):
            with self._cache_lock:
                self._stat_cache[path] = (resp, time.monotonic() + self._CACHE_TTL_SECONDS)
        return resp, b''

    def _op_create(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Create a file or directory at ``req["path"]``."""
        tau = self._connectivity.tau
        with tau.connect(
                VirtualDriveChannels.VIRTUAL_DRIVE_CREATE.value, timeout_seconds=30
        ) as s:
            s.write_string(json.dumps({
                "path": req["path"],
                "is_dir": req.get("is_dir", False),
            }) + "\n")
            resp = json.loads(s.read_all().decode())
        self._invalidate(req["path"])
        return resp, b''

    def _op_delete(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Delete the file or directory at ``req["path"]``."""
        tau = self._connectivity.tau
        with tau.connect(
                VirtualDriveChannels.VIRTUAL_DRIVE_DELETE.value, timeout_seconds=30
        ) as s:
            s.write_string(json.dumps({"path": req["path"]}) + "\n")
            resp = json.loads(s.read_all().decode())
        self._invalidate(req["path"])
        return resp, b''

    def _op_rename(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Rename or move ``req["from"]`` to ``req["to"]``."""
        tau = self._connectivity.tau
        with tau.connect(
                VirtualDriveChannels.VIRTUAL_DRIVE_RENAME.value, timeout_seconds=30
        ) as s:
            s.write_string(json.dumps({
                "from": req["from"],
                "to": req["to"],
            }) + "\n")
            resp = json.loads(s.read_all().decode())
        self._invalidate(req["from"], req["to"])
        return resp, b''

    def _op_truncate(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Resize ``req["path"]`` to ``req["new_size"]`` bytes."""
        tau = self._connectivity.tau
        with tau.connect(
                VirtualDriveChannels.VIRTUAL_DRIVE_TRUNCATE.value, timeout_seconds=30
        ) as s:
            s.write_string(json.dumps({
                "path": req["path"],
                "new_size": req["new_size"],
            }) + "\n")
            resp = json.loads(s.read_all().decode())
        self._invalidate(req["path"])
        return resp, b''

    # ── Read (negotiate on base channel → data on UUID channel) ───────────────

    def _op_read(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Read ``req["length"]`` bytes from ``req["path"]`` at ``req["offset"]``.

        Two-phase protocol:

        1. Negotiate on ``virtual_drive_read`` — tell Android the UUID so it
           opens the unique data channel.
        2. Receive file bytes on ``virtual_drive_read_{uuid}``.

        Two concurrent reads each open ``virtual_drive_read`` independently;
        TauSync pairs each with its own Android worker and its own channel ID,
        so there is no collision on the negotiation channel either.
        """
        tau = self._connectivity.tau
        uid = uuid.uuid4().hex[:8]

        # Phase 1 — announce session; Android opens the UUID data channel.
        with tau.connect(
                VirtualDriveChannels.VIRTUAL_DRIVE_READ.value, timeout_seconds=30
        ) as neg:
            neg.write_string(json.dumps({
                "path": req["path"],
                "offset": req["offset"],
                "length": req["length"],
                "uuid": uid,
            }) + "\n")
            neg.read_all()  # Android's "ready" ack

        # Phase 2 — receive bytes on the unique, collision-free channel.
        with tau.connect(
                f"{VirtualDriveChannels.VIRTUAL_DRIVE_READ.value}_{uid}"
        ) as data:
            file_bytes = data.read_all()

        return {"ok": True}, file_bytes

    # ── Write (negotiate on base channel → persistent UUID data stream) ────────

    def _op_write_open(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Open a write session for ``req["path"]``.

        Negotiates a UUID with Android on ``virtual_drive_write``, then opens
        and holds a persistent stream on ``virtual_drive_write_{uuid}``.
        The stream is stored in ``_write_sessions`` keyed by virtual path and
        used by subsequent ``write`` ops until ``write_close`` is received.
        """
        tau = self._connectivity.tau
        uid = uuid.uuid4().hex[:8]

        # Announce session; Android opens virtual_drive_write_{uid}.
        with tau.connect(
                VirtualDriveChannels.VIRTUAL_DRIVE_WRITE.value, timeout_seconds=30
        ) as neg:
            neg.write_string(json.dumps({"path": req["path"], "uuid": uid}) + "\n")
            neg.read_all()  # Android ack

        # Open and HOLD the data stream for this write session.
        stream = tau.connect(
            f"{VirtualDriveChannels.VIRTUAL_DRIVE_WRITE.value}_{uid}"
        ).__enter__()
        with self._write_sessions_lock:
            self._write_sessions[req["path"]] = stream
        return {"ok": True}, b''

    def _op_write(self, req: dict, payload: bytes) -> tuple[dict, bytes]:
        """Stream a chunk into the active write session for ``req["path"]``.

        ``stream.write(bytes) -> int`` blocks until the chunk is delivered over
        Wi-Fi, so Explorer's progress bar reflects real transfer speed. The
        lock only guards the dict lookup; the blocking write happens outside it.
        """
        with self._write_sessions_lock:
            stream = self._write_sessions.get(req["path"])
        if stream is None:
            return {"ok": False, "error": "no_write_session"}, b''
        stream.write(payload)
        return {"ok": True}, b''

    def _op_write_close(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Close the active write session so Android finalizes the file.

        Pops the stream from ``_write_sessions`` before calling ``__exit__``
        so a failure during close does not leave a leaked open channel.
        """
        with self._write_sessions_lock:
            stream = self._write_sessions.pop(req["path"], None)
        if stream is None:
            # write_open was never called or already closed — no-op.
            return {"ok": True}, b''
        # Android sees EOF when the stream closes and renames temp → final path.
        stream.__exit__(None, None, None)
        # The file's size/mtime changed and its parent listing now includes it.
        self._invalidate(req["path"])
        return {"ok": True}, b''

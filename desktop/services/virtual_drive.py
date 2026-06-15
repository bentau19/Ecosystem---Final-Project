import json
import struct
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from PySide6.QtCore import QObject, Signal

from domain.enums.virtual_drive_channels import VirtualDriveChannels
from native import Server
from services.connectivity import ConnectivityService


class VirtualDriveService(QObject):
    """Pipe server that bridges VirtualDrive.exe WinFsp ops to Android via TauSync.

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
        # Active write sessions: virtual path → open TauSync stream
        self._write_sessions: dict[str, Any] = {}

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
            self._executor = ThreadPoolExecutor(max_workers=2)
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
        # Create the named pipe server once; reconnect in a loop.
        pipe = Server(65536, 65536, self._PIPE_NAME, byte_stream=True)
        while self._is_running.is_set():
            try:
                pipe.wait_for_client(timeout=timedelta(seconds=3))
                self._handle_connection(pipe)
            except TimeoutError:
                continue
            except Exception as exc:
                self.drive_error.emit(str(exc))
            finally:
                pipe.disconnect()

    def _handle_connection(self, pipe: Any) -> None:
        # Serve one connected VirtualDrive.exe session.
        # The C++ _pipeMtx serialises all requests so this loop is strictly
        # sequential — no concurrent ops arrive on a single connection.
        while self._is_running.is_set():
            try:
                req, payload = self._read_frame(pipe)
            except Exception:
                # Pipe broken or client disconnected — exit the session loop.
                break
            try:
                resp, resp_payload = self._dispatch(req, payload)
            except Exception as exc:
                resp, resp_payload = {"ok": False, "error": str(exc)}, b''
            self._write_frame(pipe, resp, resp_payload)

    # ── Frame helpers (mirror of Protocol.cpp) ─────────────────────────────────

    def _read_frame(self, pipe: Any) -> tuple[dict, bytes]:
        """Read one framed message from the pipe.

        Frame layout (matches ``Protocol.h``):
            [4B LE jsonLen][json bytes][4B LE payloadLen][payload bytes]
        """
        json_len = struct.unpack_from('<I', pipe.read_exact(4))[0]
        j        = pipe.read_exact(json_len)
        pay_len  = struct.unpack_from('<I', pipe.read_exact(4))[0]
        payload  = pipe.read_exact(pay_len) if pay_len else b''
        return json.loads(j), payload

    def _write_frame(self, pipe: Any, resp: dict, payload: bytes = b'') -> None:
        """Write one framed response to the pipe."""
        j = json.dumps(resp).encode('utf-8')
        pipe.write(
            struct.pack('<I', len(j)) + j +
            struct.pack('<I', len(payload)) + payload
        )

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
            "list":        self._op_list,
            "stat":        self._op_stat,
            "read":        self._op_read,
            "write_open":  self._op_write_open,
            "write":       self._op_write,
            "write_close": self._op_write_close,
            "create":      self._op_create,
            "delete":      self._op_delete,
            "rename":      self._op_rename,
            "truncate":    self._op_truncate,
        }
        handler = handlers.get(op)
        if handler is None:
            return {"ok": False, "error": f"unknown op: {op}"}, b''
        return handler(req, payload)

    # ── One-shot ops (fixed meeting word) ──────────────────────────────────────

    def _op_list(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """List directory entries at ``req["path"]``."""
        tau = self._connectivity.tau
        with tau.connect(VirtualDriveChannels.VIRTUAL_DRIVE_LIST) as s:
            s.write_string(json.dumps({"path": req["path"]}))
            return json.loads(s.read_all().decode()), b''

    def _op_stat(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Return metadata for the file or directory at ``req["path"]``."""
        tau = self._connectivity.tau
        with tau.connect(VirtualDriveChannels.VIRTUAL_DRIVE_STAT) as s:
            s.write_string(json.dumps({"path": req["path"]}))
            return json.loads(s.read_all().decode()), b''

    def _op_create(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Create a file or directory at ``req["path"]``."""
        tau = self._connectivity.tau
        with tau.connect(VirtualDriveChannels.VIRTUAL_DRIVE_CREATE) as s:
            s.write_string(json.dumps({
                "path":   req["path"],
                "is_dir": req.get("is_dir", False),
            }))
            return json.loads(s.read_all().decode()), b''

    def _op_delete(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Delete the file or directory at ``req["path"]``."""
        tau = self._connectivity.tau
        with tau.connect(VirtualDriveChannels.VIRTUAL_DRIVE_DELETE) as s:
            s.write_string(json.dumps({"path": req["path"]}))
            return json.loads(s.read_all().decode()), b''

    def _op_rename(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Rename or move ``req["from"]`` to ``req["to"]``."""
        tau = self._connectivity.tau
        with tau.connect(VirtualDriveChannels.VIRTUAL_DRIVE_RENAME) as s:
            s.write_string(json.dumps({
                "from": req["from"],
                "to":   req["to"],
            }))
            return json.loads(s.read_all().decode()), b''

    def _op_truncate(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Resize ``req["path"]`` to ``req["new_size"]`` bytes."""
        tau = self._connectivity.tau
        with tau.connect(VirtualDriveChannels.VIRTUAL_DRIVE_TRUNCATE) as s:
            s.write_string(json.dumps({
                "path":     req["path"],
                "new_size": req["new_size"],
            }))
            return json.loads(s.read_all().decode()), b''

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
        with tau.connect(VirtualDriveChannels.VIRTUAL_DRIVE_READ) as neg:
            neg.write_string(json.dumps({
                "path":   req["path"],
                "offset": req["offset"],
                "length": req["length"],
                "uuid":   uid,
            }))
            neg.read_all()  # Android's "ready" ack

        # Phase 2 — receive bytes on the unique, collision-free channel.
        with tau.connect(
            f"{VirtualDriveChannels.VIRTUAL_DRIVE_READ}_{uid}"
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
        with tau.connect(VirtualDriveChannels.VIRTUAL_DRIVE_WRITE) as neg:
            neg.write_string(json.dumps({"path": req["path"], "uuid": uid}))
            neg.read_all()  # Android ack

        # Open and HOLD the data stream for this write session.
        stream = tau.connect(
            f"{VirtualDriveChannels.VIRTUAL_DRIVE_WRITE}_{uid}"
        ).__enter__()
        self._write_sessions[req["path"]] = stream
        return {"ok": True}, b''

    def _op_write(self, req: dict, payload: bytes) -> tuple[dict, bytes]:
        """Stream a chunk into the active write session for ``req["path"]``.

        ``stream.write(bytes) -> int`` blocks until the chunk is delivered over
        WiFi, so Explorer's progress bar reflects real transfer speed.
        """
        self._write_sessions[req["path"]].write(payload)
        return {"ok": True}, b''

    def _op_write_close(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Close the active write session so Android finalises the file.

        Pops the stream from ``_write_sessions`` before calling ``__exit__``
        so a failure during close does not leave a leaked open channel.
        """
        stream = self._write_sessions.pop(req["path"], None)
        if stream is None:
            # write_open was never called or already closed — no-op.
            return {"ok": True}, b''
        # Android sees EOF when the stream closes and renames temp → final path.
        stream.__exit__(None, None, None)
        return {"ok": True}, b''

import bisect
import contextlib
import json
import logging
import os
import struct
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from PySide6.QtCore import QObject, Signal

from domain.entities.device_info import DeviceEntity
from domain.enums.virtual_drive_channels import VirtualDriveChannels
from native import Server
from services.connectivity import ConnectivityService
from services.device_info import DeviceInfoService

logger = logging.getLogger(__name__)


class VirtualDriveService(QObject):
    r"""Pipe server that bridges VirtualDrive.exe WinFsp ops to Android via TauSync.

    SyncDose.exe listens on ``\\\\.\pipe\SyncDoseVDrive`` (byte-stream mode).
    VirtualDrive.exe connects and sends framed requests; this service dispatches
    each ``"op"`` to the appropriate TauSync channel and writes a framed response.

    Every request opens its own unique ``{op}_{uuid}`` TauSync meeting word
    (e.g. ``virtual_drive_stat_a1b2c3d4``). This is required for concurrency:
    connections are served in parallel, and both the PC's ``_inFlightWords`` and
    Android's ``inProgressChannels`` guards reject a *second* concurrent
    ``connect()`` on the same word. Unique words per request guarantee no two
    concurrent ops ever collide. Android routes each dynamic word to the correct
    handler via its registry prefix fallback (``channel.startsWith(prefix)``).

    Each op is a single round-trip on its own channel:

    - Metadata ops (list/stat/create/delete/rename/truncate): write a JSON
      request line, read a JSON response.
    - ``volume``: answered locally from the device-info service's latest
      ``DeviceEntity`` snapshot (no TauSync round-trip) so Explorer shows the
      phone's real total/free storage.
    - ``read``: write a ``{path, offset, length}`` request line, then read the
      file bytes back on the same stream.
    - ``write``: write a ``{path}`` header line, then stream chunks (forwarded
      from VirtualDrive.exe ``write`` ops) until ``write_close`` closes the
      stream — Android sees EOF and renames temp -> final.

    Lifecycle is managed externally: ``start()`` on ``device_connected``,
    ``stop()`` on ``device_disconnected``.

    Signals:
        drive_error (str): Emitted when a fatal pipe-level error occurs.
    """

    drive_error: Signal = Signal(str)

    # ─ Server capacity ───────────────────────────────────────────────────────
    _PIPE_NAME: str = r'\\.\pipe\SyncDoseVDrive'
    # Must be >= C++ PIPE_POOL_SIZE (12); +1 extra worker runs the accept loop.
    _MAX_CONNECTIONS: int = 12
    # How long a worker blocks for the next frame before re-checking _is_running.
    _READ_POLL: timedelta = timedelta(seconds=2)

    # ─ Session timeout ───────────────────────────────────────────────────────
    _WRITE_SESSION_TIMEOUT_S: float = 300.0  # 5 minutes

    # ─ Connect timeouts ──────────────────────────────────────────────────────
    _LIST_FULL_TIMEOUT_S: int = 60
    # Short so a slow phone causes Explorer lag, not a frozen pipe pool.
    _META_CONNECT_TIMEOUT_S: int = 3
    # Read/write ops stream large payloads — allow more time to establish the channel.
    _DATA_CONNECT_TIMEOUT_S: int = 30

    # ─ Read / stall timeouts ─────────────────────────────────────────────────
    # Time-since-last-byte stall timer; slow-but-steady links still complete.
    _READ_STALL_TIMEOUT_S: float = 10.0
    _READ_TOTAL_TIMEOUT_S: float = 300.0
    _READ_WATCHDOG_POLL_S: float = 0.5
    # Kept below C++ PIPE_META_TIMEOUT (10 s) so desktop always replies first.
    _META_STALL_TIMEOUT_S: float = 3.0

    # ─ Connection gate ───────────────────────────────────────────────────────
    # Ops gated on connectivity. Exemptions:
    #   volume     — answered from cached DeviceEntity; no TauSync round-trip.
    #   write      — write_open is gated; subsequent chunk writes follow an
    #   write_close  already-established session and must not be blocked mid-file.
    _CONNECTION_REQUIRED_OPS: frozenset[str] = frozenset({
        "list", "list_page", "stat", "read",
        "create", "delete", "rename", "truncate", "write_open",
    })

    def __init__(
            self,
            connectivity: ConnectivityService,
            device_info: DeviceInfoService,
            parent: QObject | None = None,
    ) -> None:
        """Initialize with the shared connectivity and device-info services.

        Args:
            connectivity: Application-level connectivity service; ``tau`` is
                read per-call so reconnects are handled transparently.
            device_info: Application-level device-info service. Its
                ``device_info_ready`` signal carries the connected
                :class:`~domain.entities.device_info.DeviceEntity`, whose
                ``storage_total`` / ``storage_used`` fields back the WinFsp
                ``GetVolumeInfo`` callback (the ``volume`` op). Because device
                info is refreshed periodically, the cached entity — and thus the
                drive's reported free space — stays current without any extra
                round-trip to the phone.
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._connectivity: ConnectivityService = connectivity
        self._device_info: DeviceInfoService = device_info
        self._is_running: threading.Event = threading.Event()
        self._device_lock: threading.Lock = threading.Lock()
        self._current_device: DeviceEntity | None = None  # written on Qt thread, read on pipe workers
        device_info.device_info_ready.connect(self._on_device_info)
        self._executor: ThreadPoolExecutor | None = None
        self._process: subprocess.Popen | None = None
        self._lifecycle_lock: threading.Lock = threading.Lock()
        self._write_sessions_lock: threading.Lock = threading.Lock()
        self._write_sessions: dict[str, Any] = {}
        self._write_session_start_times: dict[str, float] = {}
        self._open_pipes_lock: threading.Lock = threading.Lock()
        self._open_pipes: set[Any] = set()  # tracked so _stop() can force-close in-flight connections
        # Pre-built once to avoid per-request dict allocation in _dispatch.
        # Ordered by CRUD: Read → Create → Update → Delete.
        self._dispatch_table: dict[str, Any] = {
            # Read
            "list":        self._op_list,
            "list_page":   self._op_list_page,
            "stat":        self._op_stat,
            "volume":      self._op_volume,
            "read":        self._op_read,
            # Create
            "create":      self._op_create,
            "write_open":  self._op_write_open,
            # Update
            "write":       self._op_write,
            "write_close": self._op_write_close,
            "rename":      self._op_rename,
            "truncate":    self._op_truncate,
            # Delete
            "delete":      self._op_delete,
        }

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
            self._executor = ThreadPoolExecutor(max_workers=self._MAX_CONNECTIONS + 1)
            self._executor.submit(self._serve_loop)
            self._launch_exe()
            threading.Thread(target=self._watchdog_write_sessions, daemon=True).start()
            threading.Thread(target=self._watchdog_exe, daemon=True).start()

    def _stop(self) -> None:
        # Runs on a bare thread so shutdown(wait=True) cannot deadlock the executor.
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
            if self._process is not None and self._process.poll() is None:
                self._process.terminate()
            self._process = None
            executor = self._executor  # capture inside lock; _start() may swap self._executor after release

        # disconnect (not close) so each worker thread closes its own handle in _serve_connection's finally
        with self._open_pipes_lock:
            pipes = list(self._open_pipes)
        for pipe in pipes:
            try:
                pipe.disconnect()
            except Exception:
                pass

        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)

        with self._write_sessions_lock:
            for stream in self._write_sessions.values():
                try:
                    stream.close()
                except Exception:
                    pass
            self._write_sessions.clear()
            self._write_session_start_times.clear()

    # ── Exe management ────────────────────────────────────────────────────────

    @staticmethod
    def _find_exe() -> str:
        # Return path to VirtualDrive.exe for frozen (PyInstaller) or dev builds.
        if getattr(sys, 'frozen', False):
            return os.path.join(
                sys._MEIPASS, 'native', 'windows', 'virtual_drive', 'VirtualDrive.exe',
            )
        desktop_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(
            desktop_root, 'native', 'windows', 'virtual_drive',
            'build', 'Release', 'VirtualDrive.exe',
        )

    def _launch_exe(self) -> None:
        # Spawn VirtualDrive.exe without a console window.
        exe = self._find_exe()
        if not os.path.isfile(exe):
            self.drive_error.emit(f"VirtualDrive.exe not found: {exe}")
            return
        try:
            self._process = subprocess.Popen(
                [exe],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as exc:
            self.drive_error.emit(f"Failed to launch VirtualDrive.exe: {exc}")

    # ── Device-info cache ──────────────────────────────────────────────────────

    def _on_device_info(self, entity: object) -> None:
        # Cache latest device entity for _op_volume reads.
        with self._device_lock:
            self._current_device = entity if isinstance(entity, DeviceEntity) else None

    # ── Connectivity-noise classifier ─────────────────────────────────────────

    @staticmethod
    def _is_connectivity_exc(exc: BaseException) -> bool:
        # True for expected teardown I/O errors (aborted, broken pipe, eof, etc.).
        msg = str(exc).lower()
        return any(kw in msg for kw in (
            "aborted",
            "not connected",
            "broken pipe",
            "connection reset",
            "disconnected",
            "eof",
        ))

    # ── Pipe server loop ───────────────────────────────────────────────────────

    def _serve_loop(self) -> None:
        # Accept loop: each accepted connection is handed off to its own worker thread.
        while self._is_running.is_set():
            pipe = Server(65536, 65536, self._PIPE_NAME, byte_stream=True)
            try:
                pipe.wait_for_client(timeout=timedelta(seconds=3))
            except TimeoutError:
                pipe.close()
                continue
            except Exception as exc:
                if self._is_running.is_set() and not self._is_connectivity_exc(exc):
                    self.drive_error.emit(str(exc))
                pipe.close()
                continue
            with self._open_pipes_lock:
                self._open_pipes.add(pipe)
            self._executor.submit(self._serve_connection, pipe)

    def _serve_connection(self, pipe: Any) -> None:
        # Serve one connected pipe instance; clean up on exit.
        try:
            self._handle_connection(pipe)
        except Exception as exc:
            if not self._is_connectivity_exc(exc):
                self.drive_error.emit(str(exc))
        finally:
            with self._open_pipes_lock:
                self._open_pipes.discard(pipe)
            try:
                pipe.disconnect()
                pipe.close()
            except Exception:
                pass

    def _handle_connection(self, pipe: Any) -> None:
        # Serve sequential request→response pairs on one connection.
        while self._is_running.is_set():
            try:
                req, payload, = self._read_frame(pipe, self._READ_POLL)
                logger.debug("req: %s, payload_len: %d", req, len(payload))
            except TimeoutError:
                continue
            except Exception:
                break
            try:
                resp, resp_payload, = self._dispatch(req, payload)
                logger.debug("resp: %s, payload_len: %d", resp, len(resp_payload))
            except Exception as exc:
                if not self._is_connectivity_exc(exc):
                    self.drive_error.emit(f"op {req.get('op')!r} failed: {exc}")
                resp, resp_payload, = {"ok": False, "error": str(exc)}, b''
            try:
                self._write_frame(pipe, resp, resp_payload)
            except Exception:
                break

    # ── Frame helpers (mirror of Protocol.cpp) ─────────────────────────────────

    @staticmethod
    def _read_frame(pipe: Any, header_timeout: timedelta | None = None) -> tuple[dict, bytes]:
        # Read one [4B jsonLen][4B payLen][json][payload] frame from the pipe.
        header = pipe.read_exact(8, header_timeout)
        json_len, pay_len = struct.unpack_from('<II', header)
        body = pipe.read_exact(json_len + pay_len) if (json_len + pay_len) else b''
        return json.loads(body[:json_len]), body[json_len:]

    @staticmethod
    def _write_frame(pipe: Any, resp: dict, payload: bytes = b'') -> None:
        # Write one [4B jsonLen][4B payLen][json][payload] frame to the pipe.
        j = json.dumps(resp).encode('utf-8')
        pipe.write(struct.pack('<II', len(j), len(payload)) + j + payload)

    # ── Dispatch ───────────────────────────────────────────────────────────────

    def _dispatch(self, req: dict, payload: bytes) -> tuple[dict, bytes]:
        # Route a request to the appropriate op handler.
        op = req.get("op", "")
        if op in self._CONNECTION_REQUIRED_OPS and not self._connectivity.connected:
            # Fail fast while disconnected to avoid blocking a thread on a doomed connect.
            return {"ok": False, "error": "not_connected"}, b''
        handler = self._dispatch_table.get(op)
        if handler is None:
            return {"ok": False, "error": f"unknown op: {op}"}, b''
        return handler(req, payload)

    # ── Meeting-word helper ────────────────────────────────────────────────────

    @staticmethod
    def _unique_word(base: str) -> str:
        # Return collision-free meeting word {base}_{uuid8} for one request.
        return f"{base}_{uuid.uuid4().hex[:8]}"

    # ── Read ops ──────────────────────────────────────────────────────────────

    def _op_list(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # List directory entries at req["path"].
        resp = self._json_exchange(
            VirtualDriveChannels.VIRTUAL_DRIVE_LIST.value,
            {"path": req["path"]},
            self._META_CONNECT_TIMEOUT_S,
            stall_s=self._META_STALL_TIMEOUT_S,
        )
        return resp, b''

    def _op_list_page(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Return a page of sorted entries starting after req["after"].
        path = req["path"]
        after = req.get("after")
        limit = int(req.get("limit", 200))

        entries = self._fetch_listing_full(path)
        return self._page_entries(entries, after, limit), b''

    def _fetch_listing_full(self, path: str) -> list[dict]:
        # Fetch the full sorted directory listing from Android in one round-trip.
        resp = self._json_exchange(
            VirtualDriveChannels.VIRTUAL_DRIVE_LIST_FULL.value,
            {"path": path},
            self._LIST_FULL_TIMEOUT_S,
        )
        if not resp.get("ok"):
            return []
        entries = resp.get("entries", [])
        entries.sort(key=lambda e: e["name"])
        return entries

    @staticmethod
    def _page_entries(entries: list[dict], after: str | None, limit: int) -> dict:
        # Slice one page out of the full sorted listing using a binary-search cursor.
        if after is None:
            start = 0
        else:
            start = bisect.bisect_right(entries, after, key=lambda e: e["name"])
        page = entries[start:start + limit]
        end = start + len(page)
        return {
            "ok": True,
            "entries": page,
            "has_more": end < len(entries),
            # Must be "" not null: nlohmann j.value("next_after","") only falls back when
            # the key is absent; a present-null value raises type_error.302 in VirtualDrive.exe.
            "next_after": page[-1]["name"] if page else "",
        }

    def _op_stat(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Return metadata for req["path"].
        resp = self._json_exchange(
            VirtualDriveChannels.VIRTUAL_DRIVE_STAT.value,
            {"path": req["path"]},
            self._META_CONNECT_TIMEOUT_S,
            stall_s=self._META_STALL_TIMEOUT_S,
        )
        return resp, b''

    def _op_volume(self, _req: dict, _: bytes) -> tuple[dict, bytes]:
        # Report connected device storage from cached DeviceEntity (no TauSync round-trip).
        gb_to_bytes = 1000 ** 3
        with self._device_lock:
            device = self._current_device
        if device is None:
            return {"ok": False}, b''
        total_bytes = int(device.storage_total * gb_to_bytes)
        free_gb = max(device.storage_total - device.storage_used, 0.0)
        free_bytes = int(free_gb * gb_to_bytes)
        return {"ok": True, "total": total_bytes, "free": free_bytes}, b''

    # ── Create ops ────────────────────────────────────────────────────────────

    def _op_create(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Create a file or directory at req["path"].
        resp = self._json_exchange(
            VirtualDriveChannels.VIRTUAL_DRIVE_CREATE.value,
            {"path": req["path"], "is_dir": req.get("is_dir", False)},
            self._META_CONNECT_TIMEOUT_S,
            stall_s=self._META_STALL_TIMEOUT_S,
        )
        return resp, b''

    def _op_write_open(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Open a write session: connect a unique channel and hold the stream open.
        tau = self._connectivity.tau
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_WRITE.value)

        stream = tau.connect(word, timeout_seconds=self._DATA_CONNECT_TIMEOUT_S)
        try:
            stream.write_string(json.dumps({"path": req["path"]}) + "\n")
        except Exception:
            stream.close()
            raise
        with self._write_sessions_lock:
            self._write_sessions[req["path"]] = stream
            self._write_session_start_times[req["path"]] = time.monotonic()
        return {"ok": True}, b''

    # ── Update ops ────────────────────────────────────────────────────────────

    def _op_write(self, req: dict, payload: bytes) -> tuple[dict, bytes]:
        # Stream a chunk into the active write session for req["path"].
        with self._write_sessions_lock:
            stream = self._write_sessions.get(req["path"])
        if stream is None:
            return {"ok": False, "error": "no_write_session"}, b''
        stream.write(payload)
        return {"ok": True}, b''

    def _op_write_close(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Close the write session so Android finalizes the file.
        with self._write_sessions_lock:
            stream = self._write_sessions.pop(req["path"], None)
            self._write_session_start_times.pop(req["path"], None)
        if stream is None:
            return {"ok": True}, b''
        # EOF on close signals Android to rename temp → final path.
        stream.close()
        return {"ok": True}, b''

    def _op_rename(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Rename or move req["from"] to req["to"].
        resp = self._json_exchange(
            VirtualDriveChannels.VIRTUAL_DRIVE_RENAME.value,
            {"from": req["from"], "to": req["to"]},
            self._META_CONNECT_TIMEOUT_S,
            stall_s=self._META_STALL_TIMEOUT_S,
        )
        return resp, b''

    def _op_truncate(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Resize req["path"] to req["new_size"] bytes.
        resp = self._json_exchange(
            VirtualDriveChannels.VIRTUAL_DRIVE_TRUNCATE.value,
            {"path": req["path"], "new_size": req["new_size"]},
            self._META_CONNECT_TIMEOUT_S,
            stall_s=self._META_STALL_TIMEOUT_S,
        )
        return resp, b''

    # ── Delete ops ────────────────────────────────────────────────────────────

    def _op_delete(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Delete the file or directory at req["path"].
        resp = self._json_exchange(
            VirtualDriveChannels.VIRTUAL_DRIVE_DELETE.value,
            {"path": req["path"]},
            self._META_CONNECT_TIMEOUT_S,
            stall_s=self._META_STALL_TIMEOUT_S,
        )
        return resp, b''

    # ── JSON exchange helper (used by all metadata ops) ────────────────────────

    def _json_exchange(
            self,
            base_word: str,
            request: dict,
            connect_timeout: int,
            stall_s: float | None = None,
            total_s: float | None = None,
    ) -> dict:
        # One bounded JSON request/response on a fresh unique meeting word.
        tau = self._connectivity.tau
        word = self._unique_word(base_word)
        try:
            with tau.connect(word, timeout_seconds=connect_timeout) as s:
                s.write_string(json.dumps(request) + "\n")
                body = self._read_all_bounded(s, stall_s, total_s)
            return json.loads(body.decode())
        except TimeoutError:
            return {"ok": False, "error": "timeout"}

    # ── Read op and bounded-I/O helpers ────────────────────────────────────────

    def _op_read(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Read req["length"] bytes from req["path"] at req["offset"].
        tau = self._connectivity.tau
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_READ.value)
        path = req["path"]
        with tau.connect(word, timeout_seconds=self._DATA_CONNECT_TIMEOUT_S) as s:
            s.write_string(json.dumps({
                "path": path,
                "offset": req["offset"],
                "length": req["length"],
            }) + "\n")
            try:
                header_line = self._read_line_bounded(s)
                if not header_line:
                    self._log_read_error(path, req, "empty header (peer closed)")
                    return {"ok": False, "error": "io_error"}, b''
                try:
                    header = json.loads(header_line.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._log_read_error(path, req, f"bad header: {header_line!r}")
                    return {"ok": False, "error": "io_error"}, b''
                if not header.get("ok", False):
                    error = header.get("error", "io_error")
                    self._log_read_error(path, req, f"android error: {error}")
                    return {"ok": False, "error": error}, b''
                expected = int(header.get("length", 0))
                file_bytes = self._read_exact_bounded(s, expected)
            except TimeoutError:
                self._log_read_error(path, req, "stalled")
                return {"ok": False, "error": "timeout"}, b''
        if len(file_bytes) != expected:
            self._log_read_error(
                path, req, f"truncated: got {len(file_bytes)}/{expected} bytes")
            return {"ok": False, "error": "io_error"}, b''
        return {"ok": True}, file_bytes

    def _log_read_error(self, path: str, req: dict, reason: str) -> None:
        # Log a read failure with path, offset, length, and reason.
        logger.warning(
            "vdrive read failed: path=%s offset=%s length=%s: %s",
            path, req.get("offset"), req.get("length"), reason,
        )

    @contextlib.contextmanager
    def _read_deadline(
            self,
            s: Any,
            stall_s: float | None = None,
            total_s: float | None = None,
    ) -> Generator[tuple[Callable[[], None], threading.Event], None, None]:
        # Watchdog context manager that aborts a stalled read by closing the stream.
        stall = self._READ_STALL_TIMEOUT_S if stall_s is None else stall_s
        total = self._READ_TOTAL_TIMEOUT_S if total_s is None else total_s
        start = time.monotonic()
        last_progress = [start]
        stalled = threading.Event()
        stop_watchdog = threading.Event()

        def _watchdog() -> None:
            while not stop_watchdog.wait(self._READ_WATCHDOG_POLL_S):
                now = time.monotonic()
                if (now - last_progress[0] > stall
                        or now - start > total):
                    stalled.set()
                    s.close()
                    return

        watchdog = threading.Thread(
            target=_watchdog, name="vdrive-read-watchdog", daemon=True,
        )
        watchdog.start()

        def mark_progress() -> None:
            last_progress[0] = time.monotonic()

        try:
            yield mark_progress, stalled
        finally:
            stop_watchdog.set()
            watchdog.join(timeout=1.0)

    def _read_line_bounded(self, s: Any) -> bytes:
        # Read one \n-terminated line, aborting on stall.
        buf = bytearray()
        with self._read_deadline(s) as (mark_progress, stalled):
            while True:
                try:
                    chunk = s.read(1)
                except Exception:
                    break
                if not chunk:
                    break
                mark_progress()
                if chunk == b"\n":
                    break
                buf += chunk
        if stalled.is_set():
            raise TimeoutError("virtual-drive read header stalled")
        return bytes(buf)

    def _read_exact_bounded(self, s: Any, expected: int) -> bytes:
        # Read up to expected bytes, aborting if the transfer stalls.
        if expected <= 0:
            return b''
        parts: list[bytes] = []
        got = 0
        with self._read_deadline(s) as (mark_progress, stalled):
            while got < expected:
                try:
                    chunk = s.read(min(65536, expected - got))
                except Exception:
                    break
                if not chunk:
                    break
                parts.append(chunk)
                got += len(chunk)
                mark_progress()
        if stalled.is_set():
            raise TimeoutError("virtual-drive read stalled")
        return b"".join(parts)

    def _read_all_bounded(
            self,
            s: Any,
            stall_s: float | None = None,
            total_s: float | None = None,
    ) -> bytes:
        # Read the whole response until EOF, aborting if the read stalls.
        parts: list[bytes] = []
        with self._read_deadline(s, stall_s, total_s) as (mark_progress, stalled):
            while True:
                try:
                    chunk = s.read(65536)
                except Exception:
                    break
                if not chunk:
                    break
                parts.append(chunk)
                mark_progress()
        if stalled.is_set():
            raise TimeoutError("virtual-drive response read stalled")
        return b"".join(parts)

    # ── Watchdog threads ───────────────────────────────────────────────────────

    def _watchdog_write_sessions(self) -> None:
        # Close write sessions open longer than _WRITE_SESSION_TIMEOUT_S.
        while self._is_running.is_set():
            time.sleep(30)
            if not self._is_running.is_set():
                break
            now = time.monotonic()
            with self._write_sessions_lock:
                stale = [
                    path for path, t in self._write_session_start_times.items()
                    if now - t > self._WRITE_SESSION_TIMEOUT_S
                ]
            for path in stale:
                with self._write_sessions_lock:
                    stream = self._write_sessions.pop(path, None)
                    self._write_session_start_times.pop(path, None)
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
                self.drive_error.emit(f"Write session timed out and was closed: {path}")

    def _watchdog_exe(self) -> None:
        # Restart VirtualDrive.exe if it exits unexpectedly while running.
        while self._is_running.is_set():
            time.sleep(5)
            if not self._is_running.is_set():
                break
            with self._lifecycle_lock:
                proc = self._process
                running = self._is_running.is_set()
            if running and proc is not None and proc.poll() is not None:
                self._stop()
                self.drive_error.emit(
                    "VirtualDrive.exe exited unexpectedly — restarting"
                )
                self._start()
                return  # _start() spawned a fresh watchdog; this thread exits.

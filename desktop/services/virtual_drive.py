import json
import os
import struct
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from PySide6.QtCore import QObject, Signal

from domain.entities.device_info import DeviceEntity
from domain.enums.virtual_drive_channels import VirtualDriveChannels
from native import Server
from services.connectivity import ConnectivityService
from services.device_info import DeviceInfoService


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

    # Pipe name SyncDose exposes for VirtualDrive.exe.
    _PIPE_NAME: str = r'\\.\pipe\SyncDoseVDrive'

    # Seconds a cached stat/list entry stays valid before a fresh round-trip is
    # forced. Bounds how stale phone-side changes can appear; mutations made
    # through this service invalidate their paths immediately regardless.
    _CACHE_TTL_SECONDS: float = 30.0

    # Max concurrent VirtualDrive.exe connections served in parallel. Must be
    # >= the C++ client's pipe-pool size so every pooled connection can be
    # accepted and handled on its own thread. The +1 worker runs the accept loop.
    _MAX_CONNECTIONS: int = 8

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
        # Latest connected-device snapshot, refreshed on every device-info read.
        # Guarded by _device_lock because _on_device_info runs on the Qt event
        # thread while _op_volume reads it from a pipe-worker thread.
        self._device_lock: threading.Lock = threading.Lock()
        self._current_device: DeviceEntity | None = None
        device_info.device_info_ready.connect(self._on_device_info)
        self._executor: ThreadPoolExecutor | None = None
        self._process: subprocess.Popen | None = None
        self._lifecycle_lock: threading.Lock = threading.Lock()
        # Active write sessions: virtual path → open TauSync stream. Now that
        # connections are served concurrently, mutations are guarded by a lock.
        self._write_sessions_lock: threading.Lock = threading.Lock()
        self._write_sessions: dict[str, Any] = {}
        # Metadata caches: virtual path → (response_dict, expiry_monotonic).
        # _stat_cache answers `stat`; _list_cache answers `list`. TTL is 30 s,
        # covering a full browsing session without re-fetching from Android.
        # Mutations always call _invalidate() immediately so staleness is bounded.
        # Guarded by _cache_lock for concurrent pipe-worker access.
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
            # Launch the exe inside the lock so _stop() cannot race with process
            # creation. The exe retries connecting to the pipe server for 30 s,
            # so starting it after the serve_loop is submitted is safe.
            self._launch_exe()
            # Pre-warm root listing so Explorer opens without cold-start latency.
            threading.Thread(target=self._prefetch_root, daemon=True).start()

    def _stop(self) -> None:
        # _stop uses a bare thread (not executor) so it can call shutdown(wait=True)
        # without deadlocking on the same executor it is trying to stop.
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
            # Terminate the exe before draining the executor so it cannot send
            # new ops into a server that is already shutting down.
            if self._process is not None and self._process.poll() is None:
                self._process.terminate()
            self._process = None
            # Capture the executor reference inside the lock so a concurrent
            # _start() that swaps self._executor cannot have its fresh pool
            # shut down by this stop.  Shutdown runs outside the lock so a
            # racing _start() is never blocked behind it.
            executor = self._executor
        executor.shutdown(wait=True, cancel_futures=True)

        # All worker threads have exited — safe to purge shared state so the
        # next session never sees stale cache entries or dead write streams.
        with self._write_sessions_lock:
            for stream in self._write_sessions.values():
                try:
                    stream.close()
                except Exception:
                    pass
            self._write_sessions.clear()

        with self._cache_lock:
            self._stat_cache.clear()
            self._list_cache.clear()

    # ── Exe management ────────────────────────────────────────────────────────

    @staticmethod
    def _find_exe() -> str:
        # Frozen (PyInstaller): bundled under sys._MEIPASS.
        if getattr(sys, 'frozen', False):
            return os.path.join(
                sys._MEIPASS, 'native', 'windows', 'virtual_drive', 'VirtualDrive.exe',
            )
        # Dev: CMake Release output relative to the desktop/ root.
        desktop_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(
            desktop_root, 'native', 'windows', 'virtual_drive',
            'build', 'Release', 'VirtualDrive.exe',
        )

    def _launch_exe(self) -> None:
        # Spawn VirtualDrive.exe without a console window. It polls
        # \\.\pipe\SyncDoseVDrive for up to 30 s, so the pipe server (already
        # submitted to the executor above) will be ready before the first retry.
        # A global mutex inside the exe ensures only one instance ever runs;
        # a duplicate launch exits immediately without side-effects.
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

    # ── Connect-time prefetch ─────────────────────────────────────────────────

    def _prefetch_root(self) -> None:
        """Pre-warm the root and immediate subdirectory listings on connect.

        Called on a background thread after :meth:`_launch_exe`.  Waits briefly
        for VirtualDrive.exe to finish mounting before sending the first request.
        Caches root entries so the first Explorer open sees no cold-start delay,
        then fetches each immediate subdirectory (up to 10) so tree-view
        expansion feels instant too.
        """
        time.sleep(2.0)
        if not self._is_running.is_set():
            return
        try:
            resp, _ = self._op_list({"path": "/"}, b"")
            if not resp.get("ok"):
                return
            subdirs = [
                e["name"]
                for e in resp.get("entries", [])
                if e.get("is_dir") and e.get("name")
            ]
            for name in subdirs[:10]:
                if not self._is_running.is_set():
                    break
                self._op_list({"path": f"/{name}"}, b"")
        except Exception:
            pass

    # ── Device-info cache ──────────────────────────────────────────────────────

    def _on_device_info(self, entity: object) -> None:
        """Cache the latest connected-device entity for ``volume`` queries.

        Connected to :attr:`DeviceInfoService.device_info_ready`, which fires on
        every (periodic) device-info read. Stores the entity under
        :attr:`_device_lock` so :meth:`_op_volume`, running on a pipe-worker
        thread, always reads a consistent snapshot.

        Args:
            entity: The :class:`~domain.entities.device_info.DeviceEntity`
                emitted by the device-info service.
        """
        with self._device_lock:
            self._current_device = entity if isinstance(entity, DeviceEntity) else None

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
            except Exception:
                # Pipe broken or client disconnected — exit the session loop.
                break
            try:
                resp, resp_payload, = self._dispatch(req, payload)
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
            "list_page": self._op_list_page,
            "stat": self._op_stat,
            "volume": self._op_volume,
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

    # ── Meeting-word helper ────────────────────────────────────────────────────

    @staticmethod
    def _unique_word(base: str) -> str:
        """Return a collision-free meeting word ``{base}_{uuid}``.

        Each request opens its own unique word so concurrent ops never share a
        meeting word — the PC's ``_inFlightWords`` guard and Android's
        ``inProgressChannels`` guard both reject a second concurrent
        ``connect()`` on the same word. Android routes the dynamic word to the
        correct handler via its registry prefix fallback.

        Args:
            base: The op's base meeting word (a ``VirtualDriveChannels`` value).

        Returns:
            ``base`` suffixed with an 8-char hex token unique to this request.
        """
        return f"{base}_{uuid.uuid4().hex[:8]}"

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

    # ── One-shot metadata ops (unique meeting word per request) ────────────────

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
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_LIST.value)
        with tau.connect(word, timeout_seconds=30) as s:
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

    def _op_list_page(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Return a page of directory entries starting after ``req["after"]``.

        Forwards a ``virtual_drive_list_page_{uuid}`` request to Android, which
        returns entries sorted by name.  Pass ``req["after"] = None`` for the
        first page; use the returned ``next_after`` value as ``after`` on the
        next call to advance the cursor.  ``has_more`` is ``True`` when more
        entries exist beyond this page.

        Unlike ``_op_list``, this op is *not* cached at the Python layer —
        caching is done per-FileNode in C++ for the lifetime of the directory
        handle.

        Args:
            req: Must contain ``"path"`` (str), optionally ``"after"`` (str|None)
                 and ``"limit"`` (int, default 200).
        """
        tau  = self._connectivity.tau
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_LIST_PAGE.value)
        with tau.connect(word, timeout_seconds=30) as s:
            s.write_string(json.dumps({
                "path":  req["path"],
                "after": req.get("after"),   # None → JSON null → first page
                "limit": req.get("limit", 200),
            }) + "\n")
            resp = json.loads(s.read_all().decode())
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
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_STAT.value)
        with tau.connect(word, timeout_seconds=30) as s:
            s.write_string(json.dumps({"path": path}) + "\n")
            resp = json.loads(s.read_all().decode())

        if resp.get("ok"):
            with self._cache_lock:
                self._stat_cache[path] = (resp, time.monotonic() + self._CACHE_TTL_SECONDS)
        return resp, b''

    def _op_volume(self, _req: dict, _: bytes) -> tuple[dict, bytes]:
        """Report the connected device's storage for WinFsp ``GetVolumeInfo``.

        Answers from the cached :class:`DeviceEntity` populated by the
        device-info service (refreshed periodically) — no TauSync round-trip.
        ``storage_total`` / ``storage_used`` are decimal GB, so values are
        scaled back to bytes; ``free = total - used``.

        Returns:
            ``({"ok": True, "total": <bytes>, "free": <bytes>}, b'')`` when a
            device snapshot is available, else ``({"ok": False}, b'')`` so the
            VirtualDrive.exe caller falls back to its placeholder capacity until
            the first device-info read completes.
        """
        gb_to_bytes = 1000 ** 3
        with self._device_lock:
            device = self._current_device
        if device is None:
            return {"ok": False}, b''
        total_bytes = int(device.storage_total * gb_to_bytes)
        free_gb = max(device.storage_total - device.storage_used, 0.0)
        free_bytes = int(free_gb * gb_to_bytes)
        return {"ok": True, "total": total_bytes, "free": free_bytes}, b''

    def _op_create(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Create a file or directory at ``req["path"]``."""
        tau = self._connectivity.tau
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_CREATE.value)
        with tau.connect(word, timeout_seconds=30) as s:
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
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_DELETE.value)
        with tau.connect(word, timeout_seconds=30) as s:
            s.write_string(json.dumps({"path": req["path"]}) + "\n")
            resp = json.loads(s.read_all().decode())
        self._invalidate(req["path"])
        return resp, b''

    def _op_rename(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Rename or move ``req["from"]`` to ``req["to"]``."""
        tau = self._connectivity.tau
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_RENAME.value)
        with tau.connect(word, timeout_seconds=30) as s:
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
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_TRUNCATE.value)
        with tau.connect(word, timeout_seconds=30) as s:
            s.write_string(json.dumps({
                "path": req["path"],
                "new_size": req["new_size"],
            }) + "\n")
            resp = json.loads(s.read_all().decode())
        self._invalidate(req["path"])
        return resp, b''

    # ── Read (single unique channel: request line → byte stream) ───────────────

    def _op_read(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Read ``req["length"]`` bytes from ``req["path"]`` at ``req["offset"]``.

        One round-trip on a unique ``virtual_drive_read_{uuid}`` channel: write a
        ``{path, offset, length}`` request line, then read the file bytes back on
        the same stream until Android closes it (EOF). The unique word means
        concurrent reads never collide on a shared meeting word.
        """
        tau = self._connectivity.tau
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_READ.value)
        with tau.connect(word, timeout_seconds=30) as s:
            s.write_string(json.dumps({
                "path": req["path"],
                "offset": req["offset"],
                "length": req["length"],
            }) + "\n")
            file_bytes = s.read_all()
        return {"ok": True}, file_bytes

    # ── Write (single unique channel: header line → held byte stream) ──────────

    def _op_write_open(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        """Open a write session for ``req["path"]``.

        Opens a unique ``virtual_drive_write_{uuid}`` stream and writes a
        ``{path}`` header line so Android knows the target before any bytes
        arrive. The stream is then *held open* in ``_write_sessions`` keyed by
        virtual path and fed by subsequent ``write`` ops until ``write_close``.
        The unique word means concurrent write sessions never collide.
        """
        tau = self._connectivity.tau
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_WRITE.value)

        # Open and HOLD the stream; the header line tells Android the target path.
        stream = tau.connect(word, timeout_seconds=30)
        stream.write_string(json.dumps({"path": req["path"]}) + "\n")
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
        stream.close()
        # The file's size/mtime changed and its parent listing now includes it.
        self._invalidate(req["path"])
        return {"ok": True}, b''

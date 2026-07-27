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
from services.lifecycle import LifecycleFlag
from services.sessions import ReadSessionRegistry, WriteSessionRegistry
from services.vdrive_cache import CachedListing, ListingCache

logger = logging.getLogger(__name__)


class VirtualDriveService(LifecycleFlag, QObject):
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

    - Metadata ops (stat/create/delete/rename/truncate): write a JSON
      request line, read a JSON response.
    - ``list_page``: served from :class:`~services.vdrive_cache.ListingCache`.
      WinFsp enumerates a directory one page at a time but Android answers with
      the whole listing, so only the first page of an enumeration costs a
      round-trip; mutating ops evict the affected directories.
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
    # Must be >= C++ PIPE_POOL_SIZE (12). One worker per pipe slot: each acceptor
    # owns one persistent pipe instance, waits for its client, then serves it — so
    # no separate accept-loop worker is needed.
    _MAX_CONNECTIONS: int = 12
    # How long a worker blocks (waiting for a client, or for the next frame) before
    # re-checking _is_running. Bounds how long an idle acceptor lingers after stop().
    _READ_POLL: timedelta = timedelta(seconds=2)

    # ─ Session timeout ───────────────────────────────────────────────────────
    _WRITE_SESSION_TIMEOUT_S: float = 300.0  # 5 minutes
    # Read sessions are reaped on IDLE (no read), not total age — a long video may
    # keep one open for hours. A paused-and-abandoned handle is reclaimed; the C++
    # side transparently reopens a session on its next miss.
    _READ_SESSION_IDLE_TIMEOUT_S: float = 300.0  # 5 minutes idle

    # ─ Directory-listing cache ───────────────────────────────────────────────
    # WinFsp enumerates a directory one page at a time, and every page is backed
    # by a ``list_full`` round-trip that ships the WHOLE directory. Caching the
    # listing collapses that burst into a single fetch. The TTL only has to
    # outlive one enumeration (Explorer requests every page back-to-back over the
    # local pipe, microseconds apart); a few seconds also absorbs a user
    # reopening the same folder.
    _LISTING_CACHE_TTL_S: float = 5.0
    _LISTING_CACHE_MAX_DIRS: int = 8

    # ─ Connect timeouts ──────────────────────────────────────────────────────
    _LIST_FULL_TIMEOUT_S: int = 120
    # Short so a slow phone causes Explorer lag, not a frozen pipe pool.
    _META_CONNECT_TIMEOUT_S: int = 15
    # Read/write ops stream large payloads — allow more time to establish the channel.
    _DATA_CONNECT_TIMEOUT_S: int = 60

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
    #   read_close — teardown must always run so an abandoned read session's
    #                TauSync channel is freed even while disconnected.
    # read_open is gated (it opens a fresh channel). A gated `read` that fails
    # during a blip just poisons the session; the C++ side reopens on retry.
    _CONNECTION_REQUIRED_OPS: frozenset[str] = frozenset({
        "list_page", "stat", "read", "read_open",
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
        self._init_lifecycle()
        self._device_lock: threading.Lock = threading.Lock()
        self._current_device: DeviceEntity | None = None  # written on Qt thread, read on pipe workers
        device_info.device_info_ready.connect(self._on_device_info)
        self._executor: ThreadPoolExecutor | None = None
        self._process: subprocess.Popen | None = None
        self._lifecycle_lock: threading.Lock = threading.Lock()
        # In-progress write streams keyed by destination path; closing one signals
        # Android to rename temp → final.
        self._write_sessions: WriteSessionRegistry = WriteSessionRegistry()
        # Persistent read sessions: one long-lived TauSync stream per open
        # streaming file handle, reused across many {offset,length} reads so the
        # per-fetch channel handshake and Android file-open are paid once per
        # handle. Each session carries its own lock serialising request/response
        # framing (foreground reads and background prefetch share one stream).
        self._read_sessions: ReadSessionRegistry = ReadSessionRegistry()
        # Full directory listings, so the page burst WinFsp issues for one
        # directory costs a single round-trip to the phone instead of one per page.
        self._listings: ListingCache = ListingCache(
            self._LISTING_CACHE_TTL_S, self._LISTING_CACHE_MAX_DIRS)
        self._open_pipes_lock: threading.Lock = threading.Lock()
        self._open_pipes: set[Any] = set()  # tracked so _stop() can force-close in-flight connections
        # Pre-built once to avoid per-request dict allocation in _dispatch.
        # Ordered by CRUD: Read → Create → Update → Delete.
        self._dispatch_table: dict[str, Any] = {
            # Read
            "list_page":   self._op_list_page,
            "stat":        self._op_stat,
            "volume":      self._op_volume,
            "read":        self._op_read,
            "read_open":   self._op_read_open,
            "read_close":  self._op_read_close,
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
        """Shut down the pipe server on a daemon thread (fire-and-forget)."""
        threading.Thread(target=self._stop, daemon=True).start()

    # ── Private lifecycle ──────────────────────────────────────────────────────

    def _start(self) -> None:
        # Guard against double-start.
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._is_running.set()
            self._mark_started()
            # One worker per persistent pipe slot — each acceptor waits for and
            # then serves one long-lived connection, so no extra accept-loop worker
            # is needed.
            self._executor = ThreadPoolExecutor(max_workers=self._MAX_CONNECTIONS)
            # Pre-create every pipe instance BEFORE launching the exe so all
            # _MAX_CONNECTIONS instances are already listening when VirtualDrive.exe's
            # connect loop fires. Each C++ CreateFile then succeeds immediately instead
            # of hitting ERROR_PIPE_BUSY and sleeping RETRY_INTERVAL_MS between retries —
            # the dominant source of slow mounts. Creating an instance is just a
            # CreateNamedPipe call; a client can connect to it before the acceptor
            # reaches wait_for_client (ConnectNamedPipe then reports ERROR_PIPE_CONNECTED,
            # handled as success on the C++ side).
            for pipe in self._prewarm_pipes(self._MAX_CONNECTIONS):
                self._executor.submit(self._accept_and_serve, pipe)
            self._launch_exe()
            threading.Thread(target=self._watchdog_write_sessions, daemon=True).start()
            threading.Thread(target=self._watchdog_read_sessions, daemon=True).start()
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

        # disconnect (not close) to break any in-flight client so a serving acceptor
        # unblocks; each acceptor then closes its own handle via _discard_pipe. Idle
        # acceptors waiting in wait_for_client exit within _READ_POLL of the flag clear.
        with self._open_pipes_lock:
            pipes = list(self._open_pipes)
        for pipe in pipes:
            try:
                pipe.disconnect()
            except Exception:
                pass

        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)

        self._write_sessions.close_all()
        self._read_sessions.close_all()
        self._listings.clear()

        with self._lifecycle_lock:
            if not self._is_running.is_set():
                self._mark_stopped()

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

    # ── Pipe server (pre-warmed acceptor pool) ─────────────────────────────────

    def _new_server(self) -> Any:
        # Create one listening named-pipe instance (byte-stream mode for vdrive IPC).
        return Server(65536, 65536, self._PIPE_NAME, byte_stream=True)

    def _prewarm_pipes(self, count: int) -> list[Any]:
        # Create `count` listening pipe instances up front and track them so _stop()
        # can force-close any still in flight. Synchronous because CreateNamedPipe is
        # cheap and every instance must exist before the exe begins connecting.
        pipes: list[Any] = []
        for _ in range(count):
            pipe = self._new_server()
            with self._open_pipes_lock:
                self._open_pipes.add(pipe)
            pipes.append(pipe)
        return pipes

    def _accept_and_serve(self, pipe: Any) -> None:
        # Own one persistent pipe slot for the service's lifetime: wait for a client,
        # serve request/response pairs until it disconnects, then recreate a fresh
        # instance and repeat so the slot stays available across reconnects / exe
        # restarts. Exits within _READ_POLL of _is_running being cleared.
        while self._is_running.is_set():
            try:
                pipe.wait_for_client(timeout=self._READ_POLL)
            except TimeoutError:
                continue  # no client yet; re-check _is_running and keep waiting
            except Exception as exc:
                if self._is_running.is_set() and not self._is_connectivity_exc(exc):
                    self.drive_error.emit(str(exc))
                pipe = self._recycle_pipe(pipe)
                if pipe is None:
                    return
                continue
            try:
                self._handle_connection(pipe)
            except Exception as exc:
                if not self._is_connectivity_exc(exc):
                    self.drive_error.emit(str(exc))
            pipe = self._recycle_pipe(pipe)
            if pipe is None:
                return
        self._discard_pipe(pipe)

    def _recycle_pipe(self, pipe: Any) -> Any | None:
        # Close/untrack `pipe`, then (if still running) return a fresh listening
        # instance for this slot. Returns None when the service is stopping so the
        # acceptor exits.
        self._discard_pipe(pipe)
        if not self._is_running.is_set():
            return None
        try:
            fresh = self._new_server()
        except Exception as exc:
            if self._is_running.is_set() and not self._is_connectivity_exc(exc):
                self.drive_error.emit(str(exc))
            return None
        with self._open_pipes_lock:
            self._open_pipes.add(fresh)
        return fresh

    def _discard_pipe(self, pipe: Any) -> None:
        # Untrack and force-close one pipe instance, ignoring teardown I/O errors.
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

    def _op_list_page(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Serve a page out of the cached full listing, fetching from the phone
        # only on a miss. WinFsp walks every page of a directory back-to-back,
        # so one fetch answers the whole enumeration instead of one per page.
        path = req["path"]
        now = time.monotonic()

        listing = self._listings.get(path, now)
        if listing is None:
            listing = self._fetch_listing_full(path)
            if listing is None:
                # Never cache a failure, and never report it as an empty folder:
                # the C++ side maps this to a retryable I/O error so Explorer
                # retries instead of showing the directory as empty.
                return {"ok": False, "error": "io_error"}, b''
            self._listings.put(path, listing.entries, listing.dir_mtime_ms, now)

        return self._page_entries(
            listing.entries, req.get("after"), int(req.get("limit", 200))), b''

    def _fetch_listing_full(self, path: str) -> CachedListing | None:
        # Fetch the full directory listing from Android in one round-trip.
        # Returns None when the fetch failed — distinct from an empty directory,
        # which is a legitimate (and cacheable) empty entry list.
        resp = self._json_exchange(
            VirtualDriveChannels.VIRTUAL_DRIVE_LIST_FULL.value,
            {"path": path},
            self._LIST_FULL_TIMEOUT_S,
        )
        if not resp.get("ok"):
            logger.warning(
                "vdrive list_full failed: path=%s: %s",
                path, resp.get("error", "unknown"),
            )
            return None
        # Android lists via File.listFiles(), which is unordered; the page cursor
        # binary-searches on name, so sorting here is what makes paging correct.
        entries = resp.get("entries", [])
        entries.sort(key=lambda e: e["name"])
        return CachedListing(
            entries=entries,
            dir_mtime_ms=int(resp.get("dir_mtime_ms", 0)),
            fetched_at=time.monotonic(),
        )

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
        # Every mutating op evicts unconditionally, not only on success: a
        # partially-applied change must not leave a stale listing behind, and
        # over-invalidating only costs one refetch.
        self._listings.invalidate_parent(req["path"])
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
        self._write_sessions.add(req["path"], stream, time.monotonic())
        return {"ok": True}, b''

    # ── Update ops ────────────────────────────────────────────────────────────

    def _op_write(self, req: dict, payload: bytes) -> tuple[dict, bytes]:
        # Stream a chunk into the active write session for req["path"].
        session = self._write_sessions.get(req["path"])
        if session is None:
            return {"ok": False, "error": "no_write_session"}, b''
        session.stream.write(payload)
        return {"ok": True}, b''

    def _op_write_close(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Close the write session so Android finalizes the file.  drop() closes the
        # stream; the resulting EOF signals Android to rename temp → final path.
        self._write_sessions.drop(req["path"])
        # The file's size and mtime just changed — the parent listing is stale.
        self._listings.invalidate_parent(req["path"])
        return {"ok": True}, b''

    def _op_rename(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Rename or move req["from"] to req["to"].
        # Both parents lose/gain an entry; and when the source is a directory,
        # every listing beneath it is orphaned.
        self._listings.invalidate_parent(req["from"])
        self._listings.invalidate_parent(req["to"])
        self._listings.drop_subtree(req["from"])
        resp = self._json_exchange(
            VirtualDriveChannels.VIRTUAL_DRIVE_RENAME.value,
            {"from": req["from"], "to": req["to"]},
            self._META_CONNECT_TIMEOUT_S,
            stall_s=self._META_STALL_TIMEOUT_S,
        )
        return resp, b''

    def _op_truncate(self, req: dict, _: bytes) -> tuple[dict, bytes]:
        # Resize req["path"] to req["new_size"] bytes.
        self._listings.invalidate_parent(req["path"])
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
        # Deleting a directory orphans every cached listing beneath it.
        self._listings.invalidate_parent(req["path"])
        self._listings.drop_subtree(req["path"])
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

    def _op_read(self, req: dict[str, Any], _: bytes) -> tuple[dict[str, Any], bytes]:
        # Read req["length"] bytes at req["offset"]. A "session" key routes the
        # read onto the handle's persistent channel; otherwise a fresh one-shot
        # channel is opened (backward-compatible / non-streaming path).
        if "session" in req:
            return self._read_sessioned(req)
        return self._read_fresh(req)

    def _read_fresh(self, req: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        # One-shot read on a fresh unique channel. Uses the same wire protocol as a
        # session (a {path} open header then one {offset,length} request) so Android
        # serves both through the one serveReadSession loop; closing the channel
        # after the single read ends that loop via EOF.
        tau = self._connectivity.tau
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_READ.value)
        path = req["path"]
        try:
            with tau.connect(word, timeout_seconds=self._DATA_CONNECT_TIMEOUT_S) as s:
                s.write_string(json.dumps({"path": path}) + "\n")
                s.write_string(json.dumps({
                    "offset": req["offset"],
                    "length": req["length"],
                }) + "\n")
                return self._read_payload(s, path, req)
        except TimeoutError:
            self._log_read_error(path, req, "connect/stalled")
            return {"ok": False, "error": "timeout"}, b''

    def _read_sessioned(self, req: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        # Read on the handle's persistent channel (path was sent once at open).
        session_id = req["session"]
        session = self._read_sessions.get(session_id)
        if session is None:
            return {"ok": False, "error": "no_read_session"}, b''
        self._read_sessions.touch(session_id, time.monotonic())
        path = req.get("path", "?")
        # Serialise framing: foreground reads and background prefetch share this
        # one stream, so only one request/response may be in flight at a time.
        with session.lock:
            try:
                session.stream.write_string(json.dumps({
                    "offset": req["offset"],
                    "length": req["length"],
                }) + "\n")
                return self._read_payload(session.stream, path, req)
            except TimeoutError:
                # The stall watchdog closed the stream — the session is dead.
                self._log_read_error(path, req, "session stalled")
                self._read_sessions.drop(session_id)
                return {"ok": False, "error": "timeout"}, b''
            except Exception as exc:
                self._log_read_error(path, req, f"session stream error: {exc}")
                self._read_sessions.drop(session_id)
                return {"ok": False, "error": "io_error"}, b''

    def _read_payload(self, s: Any, path: str, req: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        # Read one {ok,length}\n header line then exactly `length` payload bytes.
        # Raises TimeoutError on stall (callers map it to a retryable timeout).
        #
        # One watchdog spans the whole exchange. Header and payload arrive on the
        # same stream, so a single stall/total budget for both is cheaper (one
        # thread per read op instead of one per leaf read) and stricter — the
        # total budget previously restarted between the header and the payload.
        with self._read_deadline(s) as (mark_progress, stalled):
            header_line = self._read_line_bounded(s, mark_progress)
            if not header_line:
                if stalled.is_set():
                    raise TimeoutError("virtual-drive read header stalled")
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
            file_bytes = self._read_exact_bounded(s, expected, mark_progress)

        if stalled.is_set():
            raise TimeoutError("virtual-drive read stalled")
        if len(file_bytes) != expected:
            self._log_read_error(
                path, req, f"truncated: got {len(file_bytes)}/{expected} bytes")
            return {"ok": False, "error": "io_error"}, b''
        return {"ok": True}, file_bytes

    def _op_read_open(self, req: dict[str, Any], _: bytes) -> tuple[dict[str, Any], bytes]:
        # Open a persistent read channel: connect once, send the {path} header so
        # Android opens the file, and hold the stream for many subsequent reads.
        tau = self._connectivity.tau
        word = self._unique_word(VirtualDriveChannels.VIRTUAL_DRIVE_READ.value)
        session_id = uuid.uuid4().hex
        stream = tau.connect(word, timeout_seconds=self._DATA_CONNECT_TIMEOUT_S)
        try:
            stream.write_string(json.dumps({"path": req["path"]}) + "\n")
        except Exception:
            stream.close()
            raise
        self._read_sessions.add(session_id, stream, time.monotonic())
        return {"ok": True, "session": session_id}, b''

    def _op_read_close(self, req: dict[str, Any], _: bytes) -> tuple[dict[str, Any], bytes]:
        # Close a persistent read session; Android sees EOF and releases the file.
        self._read_sessions.drop(req.get("session", ""))
        return {"ok": True}, b''

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

    @staticmethod
    def _read_line_bounded(s: Any, mark_progress: Callable[[], None]) -> bytes:
        # Read one \n-terminated line using the stream's own buffered scanner:
        # one CLR call per 4 KB instead of one per byte.
        #
        # read_until keeps any bytes that arrived after the newline in the
        # stream's internal pushback buffer, which read() drains first — so the
        # payload that follows the header on this same stream is never lost. For
        # a session that buffer lives on the stream object, which outlives the
        # individual read, so nothing extra has to be carried across calls.
        #
        # The caller's watchdog bounds this: read_until is one blocking call, so
        # a peer that never sends a newline is caught by the stall timer.
        try:
            line = s.read_until(b"\n")
        except Exception:
            return b''  # watchdog closed the stream, or the peer hung up
        mark_progress()
        return line[:-1] if line.endswith(b"\n") else line

    @staticmethod
    def _read_exact_bounded(s: Any, expected: int, mark_progress: Callable[[], None]) -> bytes:
        # Read up to expected bytes, aborting if the transfer stalls.
        if expected <= 0:
            return b''
        parts: list[bytes] = []
        got = 0
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
            for path in self._write_sessions.stale(now, self._WRITE_SESSION_TIMEOUT_S):
                if self._write_sessions.drop(path):
                    self.drive_error.emit(f"Write session timed out and was closed: {path}")

    def _watchdog_read_sessions(self) -> None:
        # Close read sessions idle (no read) longer than _READ_SESSION_IDLE_TIMEOUT_S.
        # Idle-based, not total-age: an actively-playing video keeps reading and
        # is never reaped; only an abandoned/paused handle is reclaimed.
        while self._is_running.is_set():
            time.sleep(30)
            if not self._is_running.is_set():
                break
            now = time.monotonic()
            for session_id in self._read_sessions.stale(now, self._READ_SESSION_IDLE_TIMEOUT_S):
                self._read_sessions.drop(session_id)

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

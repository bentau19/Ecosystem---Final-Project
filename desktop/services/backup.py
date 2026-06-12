from __future__ import annotations

import json
import logging
import math
import os
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from classifer import Classifier, ClassificationVerdict
from domain.dto.backup_review_prompt import BackupReviewPromptDTO
from domain.dto.backup_session_prompt import BackupSessionPromptDTO
from domain.enums.backup_channels import BackupChannels
from domain.enums.backup_file_result import BackupFileResult
from serializers.backup_session import BackupSessionSerializer
from tausync_py import TauSyncStream
from utils import network

if TYPE_CHECKING:
    from services.connectivity import ConnectivityService

# ── Backup data-channel timeout calibration ───────────────────────────────────

_BACKUP_DATA_TIMEOUT_MULT: float = 1 / 3_000_000  # 3 MB/s
_BACKUP_DATA_TIMEOUT_OFFSET_S: int = 30  # baseline before any bytes arrive

# ── Stall-detection timeout ───────────────────────────────────────────────────
# If no slot has been dispatched and no active slot worker is running for this
# many seconds, the backup is declared stalled and backup_error is emitted.
_STALL_TIMEOUT_S: float = 90.0

# ── Media-type extension sets (mirror Android BackupDataSource.MEDIA_EXTENSIONS) ─
# Split into two sets so _media_subdir can route photos and videos to separate
# top-level subdirectories inside the user-chosen destination folder.

_PHOTO_EXTENSIONS: frozenset[str] = frozenset({
    "jpg", "jpeg", "png", "gif", "bmp", "webp",
    "heic", "heif", "tiff", "tif", "avif", "raw",
    "cr2", "nef", "arw", "dng",
})

_VIDEO_EXTENSIONS: frozenset[str] = frozenset({
    "mp4", "avi", "mov", "mkv", "3gp", "webm",
    "ts", "m4v", "flv", "wmv", "mts", "m2ts",
})

# ---------------------------------------------------------------------------
# FileDetection imports — available after desktop/main.py inserts FileDetection/
# into sys.path.  Imported at module level so missing-dependency errors surface
# early (at app startup) rather than mid-backup.
# ---------------------------------------------------------------------------
from detector import is_corrupt
from file_duplicates import check_for_duplicates
from image_classifer import ClassificationResult

logger = logging.getLogger(__name__)


class BackupService(QObject):
    """Receives files from Android, screens them via FileDetection, and saves
    approved ones to a user-chosen destination folder.

    The service is passive until a device connects.  Call :meth:`start`
    (wired to ``device_connected`` in AppState) to begin waiting for Android
    manifests.

    Protocol:
        1. Android opens ``backup_manifest`` and sends a lightweight JSON
           header: ``{"file_count": N, "files_bytes": S, "classify": true|false}``.
        2. PC parses the header and emits :attr:`manifest_received` so the
           ViewModel can ask the user for a destination folder.
        3. PC blocks on ``_dest_event`` until :meth:`proceed` (user confirmed)
           or :meth:`cancel_session` (user dismissed) is called.
        4. On confirmation, PC sends ``"ready"`` on ``backup_ready_pc``.
        5. Android opens ``backup_slot_meta_0`` … ``backup_slot_meta_N`` (in
           parallel or sequentially — Android decides). Each meta channel
           carries a compact JSON object:
           ``{"name": "photo.jpg", "size": 12345, "mtime": T}``.
           PC reads the metadata with a short fixed connect timeout (~10 s),
           then immediately opens the corresponding ``backup_slot_data_N``
           channel to receive the raw file bytes with a file-size-proportional
           timeout (computed from ``size`` now known from the metadata).
           Separating the two channels removes the need to pick a
           one-size-fits-all timeout that must accommodate both tiny JSON
           payloads and multi-gigabyte file transfers.
        6. After receiving each slot the PC screens the cached file via
           :meth:`~classifer.Classifier.classify`:

           * :func:`check_for_duplicates` — exact-content hash via xxhash / SQLite
           * :func:`~image_classifer.classify_image` — ML content classifier (torch optional)

           The classifier returns a :class:`~classifer.ClassificationResult`:

           * ``ACCEPTED`` — the file passes screening and is saved.
           * ``REJECTED`` — exact duplicate, or confidently unwanted (discarded
             before it is ever copied to ``dest_dir``).
           * ``NEEDS_REVIEW`` — the ML classifier's argmax favours "remove" but
             isn't confident enough to act automatically. The file is copied to
             ``dest_dir`` and the slot is finished (see step 8) **immediately** —
             the PC then emits :attr:`review_required` with a
             :class:`~domain.dto.backup_review_prompt.BackupReviewPromptDTO` on a
             separate thread and waits for the ViewModel to call
             :meth:`resolve_review`. If the user (or a cancelled session)
             chooses to discard, the already-saved file is deleted and
             :attr:`file_skipped` is emitted. This review never blocks
             :attr:`file_complete` / the per-slot result token.

        7. Files that pass screening (``ACCEPTED`` or ``NEEDS_REVIEW``) are
           copied to the user-chosen ``dest_dir``; ``REJECTED`` files are
           discarded.
        8. Once a slot reaches a terminal state, the PC writes
           :class:`~domain.enums.backup_file_result.BackupFileResult`
           ``SUCCESS`` (``"succ"``) or ``FAILURE`` (``"fail"``) on
           ``backup_file_result_{i}`` — sent for **every** slot regardless of
           the manifest's ``classify`` flag. ``FAILURE`` is reserved for
           transport/IO problems (dropped connection, disk write error);
           PC-local screening rejections (corrupt, duplicate, or filtered by
           the ML classifier — including a post-copy ``NEEDS_REVIEW`` discard)
           are reported as ``SUCCESS`` since the transfer itself completed —
           Android only needs to know whether the bytes made it across and
           were handled, not the PC's content-screening verdict.

    Threading:
        All I/O runs on daemon ``threading.Thread`` instances — never QThread.
        PySide6 queued connections deliver signals to the main thread safely.

        At most :attr:`MAX_CONCURRENT_RECEIVES` slot transfers are connected
        to / actively reading from TauSync at once — additional slot threads
        block on a semaphore until a slot frees up. This keeps the number of
        concurrent calls across the pythonnet/.NET CLR bridge bounded, which
        avoids interop races that can corrupt reads on large backups.

        FileDetection is imported from the project-root ``FileDetection/``
        directory, which ``desktop/main.py`` adds to ``sys.path`` before any
        deferred imports.

    Signals:
        manifest_received (Signal[int, int]): Emitted with
            ``(file_count, total_size_bytes)`` once the Android manifest header
            is parsed.  The ViewModel uses this to show a folder-picker dialog.
        file_registered (Signal[str, int]): Emitted with
            ``(rel_path, size_bytes)`` when per-slot metadata is first read.
            The ViewModel uses this to lazily initialize per-file tracking
            state before any progress ticks arrive.
        file_progress (Signal[str, int, float]): Emitted at the start and end
            of each slot transfer as ``(rel_path, bytes_done, speed_bps)``.
        file_complete (Signal[str, str]): Emitted with ``(file_name, abs_dest_path)`` when a file
            passes all screening stages and is copied to the destination.
        file_failed (Signal[str, str]): Emitted with ``(rel_path, reason)``
            when a file fails due to a transport or IO error only.
        file_skipped (Signal[str]): Emitted with ``rel_path`` when a file was
            not kept locally but the transfer completed (Android receives
            ``SUCCESS``).  Covers both ML auto-rejections (duplicate /
            confident filter) and user-review removals via
            :class:`~views.widgets.backup.backup_classification_review_dialog.BackupClassificationReviewDialog`.
        review_required (Signal[object]): Emitted with a
            :class:`~domain.dto.backup_review_prompt.BackupReviewPromptDTO`
            when the ML classifier returns
            :attr:`~classifer.ClassificationVerdict.NEEDS_REVIEW` for a file.
            By the time this is emitted the file has already been saved to
            ``dest_dir`` and the slot has already finished (``file_complete``
            was emitted and the per-slot result token was sent). A dedicated
            thread waits for :meth:`resolve_review` to be called with the
            matching ``channel``; if the user discards, the saved file is
            deleted and :attr:`file_skipped` is emitted.
        backup_complete (Signal): Emitted once every file in the session has
            reached a terminal state (complete, failed, or skipped).
        backup_error (Signal[str]): Emitted when the backup session stalls —
            no slot workers are running and no new files have arrived for
            :data:`_STALL_TIMEOUT_S` seconds while undispatched slots remain.
            Carries a human-readable reason string.  The ViewModel should call
            :meth:`cancel` after receiving this signal.
    """

    # Maximum number of slot transfers that may be reading from TauSync at once.
    # Additional submitted futures queue up inside the executor without consuming
    # threads, keeping the pythonnet/.NET CLR bridge call count bounded.
    MAX_CONCURRENT_RECEIVES: int = 5

    # ── Signals ───────────────────────────────────────────────────────────────
    manifest_received: Signal = Signal(int, 'qint64', bool,
                                       bool)  # (file_count, total_size_bytes, classify, storage_saver)
    file_registered: Signal = Signal(str, 'qint64', 'qint64')  # (rel_path, size_bytes, orig_size_bytes)
    file_progress: Signal = Signal(str, 'qint64', float)  # (rel_path, bytes_done, speed_bps)
    file_complete: Signal = Signal(str, str)  # (file_name, abs_dest_path)
    file_failed: Signal = Signal(str, str)  # (rel_path, reason) — transport/IO errors only
    file_skipped: Signal = Signal(str)  # (rel_path) — transfer OK, file not kept locally
    review_required: Signal = Signal(object)  # BackupReviewPromptDTO

    backup_complete: Signal = Signal()
    backup_error: Signal = Signal(str)  # (reason) — stall or unrecoverable error

    session_paused: Signal = Signal()
    session_resumed: Signal = Signal()

    def __init__(
            self,
            connectivity: ConnectivityService,
            parent: QObject | None = None,
    ) -> None:
        """Initialize the service and prepare the detection database.

        The manifest listener is **not** started automatically.  Call
        :meth:`start` when a device connects.

        Args:
            connectivity: Shared connectivity service.  ``connectivity.tau``
                is accessed at call time so reconnects are handled
                transparently.
            parent: Optional Qt parent for memory management.
        """
        super().__init__(parent)

        self._connectivity: ConnectivityService = connectivity

        # ── Threading primitives ──────────────────────────────────────────────
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor()
        self._slot_executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=self.MAX_CONCURRENT_RECEIVES
        )
        self._is_running: threading.Event = threading.Event()
        self._dest_event: threading.Event = threading.Event()
        self._cancel_event: threading.Event = threading.Event()
        self._pause_event: threading.Event = threading.Event()

        self._dest_dir: Path | None = None
        self._lifecycle_lock: threading.Lock = threading.Lock()

        self._file_count: int | None = None
        self._classify: bool = False
        self._storage_saver: bool = False

        # ── Pending confidence reviews (NEEDS_REVIEW) ─────────────────────
        # Keyed by meta slot channel (e.g. "backup_slot_meta_0"). Protected by
        # _review_lock since multiple _receive_file threads may register/resolve concurrently.
        self._review_lock: threading.Lock = threading.Lock()
        self._pending_reviews: dict[str, threading.Event] = {}
        self._review_decisions: dict[str, bool] = {}  # True = keep, False = remove

    # ── Lifecycle (wired by AppState to device_connected / device_disconnected) ─

    def start(self) -> None:
        """Start the manifest-listener thread.

        Idempotent — silently no-ops if already running.
        """
        threading.Thread(target=self._start, daemon=True).start()

    def stop(self) -> None:
        """Stop the service and join all active threads."""
        threading.Thread(target=self._stop, daemon=True).start()

    # ── Session control (called by ViewModel after user interaction) ─────────

    def proceed(self, dest_dir: Path) -> None:
        """Unblock the coordinator with the user's chosen destination.

        Called by the ViewModel after the user confirms the folder picker.
        Safe to call from any thread.

        Args:
            dest_dir: Absolute path to the backup destination folder.
        """
        self._dest_dir = dest_dir
        self._dest_event.set()

    def cancel_session(self) -> None:
        """Abort the pending session (user dismissed the folder picker).

        Sets both the cancel and dest events so the waiting coordinator thread
        wakes up and exits cleanly.  Also sends a lightweight rejection token on
        ``BACKUP_READY_FROM_PC`` so Android's ``waitForPcReady()`` unblocks
        immediately instead of waiting out its 120-second timeout — which would
        otherwise block the phone from starting a new backup session.
        """
        self._cancel_event.set()
        self._dest_event.set()  # wake the coordinator so it can check _cancel_event
        self._wake_pending_reviews()
        # Notify Android immediately so it doesn't block for up to 120 s waiting
        # for a ready ack that will never come.  Without this the phone cannot
        # start a new backup until the timeout expires.
        if self._is_running.is_set():
            self._executor.submit(self._send_ready_rejection)

    def resolve_review(self, channel: str, keep: bool) -> None:
        """Resolve a pending :attr:`review_required` prompt.

        Called by the ViewModel after the user responds to a
        :class:`~domain.dto.backup_review_prompt.BackupReviewPromptDTO`.
        Unblocks the :meth:`_receive_file` thread waiting on *channel*. Safe
        to call from any thread; a no-op if *channel* has no pending review
        (e.g. the session ended before the user responded).

        Args:
            channel: The slot channel from the originating
                :class:`~domain.dto.backup_review_prompt.BackupReviewPromptDTO`.
            keep: ``True`` to keep the file, ``False`` to discard it.
        """
        with self._review_lock:
            event = self._pending_reviews.get(channel)
            if event is None:
                return
            self._review_decisions[channel] = keep
            event.set()

    def pause(self) -> None:
        """Pause slot transfers after the current read operation completes."""
        self._pause_event.set()
        if self._is_running.is_set():
            self._executor.submit(self._send_control_to_android, "pause")

    def resume(self) -> None:
        """Resume a paused backup session."""
        self._pause_event.clear()
        if self._is_running.is_set():
            self._executor.submit(self._send_control_to_android, "resume")

    def cancel(self) -> None:
        """Cancel an in-progress download or screening session."""
        self._cancel_event.set()
        self._pause_event.clear()  # unblock any paused slots so they can exit
        self._wake_pending_reviews()
        if self._is_running.is_set():
            self._executor.submit(self._send_control_to_android, "stop")

    def _wake_pending_reviews(self) -> None:
        # Wake every _receive_file thread blocked on a pending review so it can
        # exit via the _cancel_event check instead of waiting forever for a
        # response that will never come.
        with self._review_lock:
            for event in self._pending_reviews.values():
                event.set()

    # ── Cross-device control (Android ↔ PC) ───────────────────────────────────

    def _send_control_to_android(self, cmd: str) -> None:
        # Best-effort / fire-and-forget — failures are logged, never raised, since
        # pause/resume/stop must not block the UI thread that triggered them.
        try:
            tau = self._connectivity.tau
            network.write_string_to_channel(
                tau,
                BackupChannels.BACKUP_CONTROL_FROM_PC.value,
                json.dumps({"cmd": cmd}),
            )
        except Exception as exc:
            logger.warning("Failed to send control %r: %s", cmd, exc)

    def _send_ready_rejection(self) -> None:
        # Write "reject" on BACKUP_READY_FROM_PC so Android's waitForPcReady()
        # unblocks immediately and treats this as a PC-initiated cancel rather
        # than a network error.  Called fire-and-forget from cancel_session().
        #
        # Protocol contract: PC sends "ready" to accept a backup session;
        # any other token (including "reject") signals cancellation.
        #
        # If the connection has already dropped the write will throw — swallow
        # it here; Android will time out naturally in that case.
        try:
            tau = self._connectivity.tau
            network.write_string_to_channel(
                tau,
                BackupChannels.BACKUP_READY_FROM_PC.value,
                "reject",
                timeout_seconds=10,
            )
        except Exception as exc:
            logger.warning("Failed to send ready rejection: %s", exc)

    def _listen_android_controls(self) -> None:
        # Poll for Android-initiated pause/resume/stop commands, mirroring the
        # get_peer_waiting_words() pattern used in _get_files. Runs for the
        # lifetime of the active backup session.
        while self._is_running.is_set() and not self._cancel_event.is_set():
            try:
                waiting: list[str] = self._connectivity.tau.get_peer_waiting_words()
                if BackupChannels.BACKUP_CONTROL_FROM_ANDROID.value in waiting:
                    tau = self._connectivity.tau
                    with tau.connect(BackupChannels.BACKUP_CONTROL_FROM_ANDROID.value) as stream:
                        raw = stream.read_all().decode("utf-8").strip()
                    cmd = json.loads(raw).get("cmd", "")
                    if cmd == "pause" and not self._pause_event.is_set():
                        self._pause_event.set()
                        self.session_paused.emit()
                    elif cmd == "resume" and self._pause_event.is_set():
                        self._pause_event.clear()
                        self.session_resumed.emit()
                    elif cmd == "stop":
                        self._cancel_event.set()
                        self._pause_event.clear()
                        self._wake_pending_reviews()
                        break
                else:
                    time.sleep(0.5)
            except Exception as exc:
                if self._cancel_event.is_set():
                    break
                logger.warning("Android control listener error: %s", exc)

    # ── Timeout helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _data_timeout(file_size: int) -> int:
        """Compute a file-size-proportional connect timeout for a data channel.

        Formula: ``ceil(_BACKUP_DATA_TIMEOUT_MULT * file_size) + _BACKUP_DATA_TIMEOUT_OFFSET_S``

        Args:
            file_size: Transfer size in bytes.

        Returns:
            Timeout in whole seconds.
        """
        return math.ceil(_BACKUP_DATA_TIMEOUT_MULT * file_size) + _BACKUP_DATA_TIMEOUT_OFFSET_S

    # ── Private lifecycle ─────────────────────────────────────────────────────

    def _start(self) -> None:
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._executor = ThreadPoolExecutor()
            self._slot_executor = ThreadPoolExecutor(max_workers=self.MAX_CONCURRENT_RECEIVES)
            self._is_running.set()

    def _stop(self) -> None:
        # Executor references are captured inside the lock so a concurrent
        # _start() (which swaps both pools) can never have its fresh pools
        # shut down by this stop.
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
            self._cancel_event.set()
            self._dest_event.set()  # unblock any waiting coordinator
            self._wake_pending_reviews()
            slot_executor = self._slot_executor
            executor = self._executor
        # Slot executor first — _receive_file tasks check _cancel_event and exit
        # quickly once it is set, so this shutdown completes without a long wait.
        slot_executor.shutdown(wait=True, cancel_futures=True)
        executor.shutdown(wait=True, cancel_futures=True)

    # ── Manifest entry point (called by PhoneRequestService) ─────────────────

    def receive_manifest(self) -> None:
        """Receive a single backup manifest from Android.

        Called by :class:`~services.phone_request.PhoneRequestService` when
        ``BACKUP_MANIFEST_FROM_ANDROID`` appears in
        ``get_peer_waiting_words()``.  Submits the actual I/O to the executor
        so the ``PhoneRequestService`` polling loop is never blocked.
        """
        if not self._is_running.is_set():
            return
        self._executor.submit(self._handle_manifest)

    def _handle_manifest(self) -> None:
        # Connect once, read the manifest header, reset per-session state, and
        # hand off to the coordinator thread.  Called from the executor —
        # never from the PhoneRequestService polling loop directly.
        try:
            tau = self._connectivity.tau
            with tau.connect(BackupChannels.BACKUP_MANIFEST_FROM_ANDROID.value, timeout_seconds=5) as stream:
                raw: str = stream.read_all().decode("utf-8")
        except Exception as exc:
            logger.error("Manifest read error: %s", exc)
            return

        try:
            backup_session_data = BackupSessionSerializer.deserialize(raw)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("Manifest parse error: %s", exc)
            return

        # Reset per-session events before emitting so the coordinator never
        # sees stale state from a previous session.
        self._dest_event.clear()
        self._cancel_event.clear()
        self._pause_event.clear()
        self._dest_dir = None
        self._storage_saver = False

        # Wake any leftover post-copy review threads from a prior session
        # before clearing their bookkeeping. With _cancel_event already
        # cleared for this new session, a leftover thread will resume,
        # find no recorded decision (defaults to discard), and exit
        # cleanly instead of hanging forever.
        self._wake_pending_reviews()
        with self._review_lock:
            self._pending_reviews.clear()
            self._review_decisions.clear()

        self._file_count = backup_session_data.file_count
        self._classify = backup_session_data.classify
        self._storage_saver = backup_session_data.storage_saver

        self.manifest_received.emit(
            backup_session_data.file_count,
            backup_session_data.total_size_bytes,
            backup_session_data.classify,
            backup_session_data.storage_saver,
        )

        if self._is_running.is_set():
            self._executor.submit(self._wait_for_dir, backup_session_data)

    # ── Coordinator thread ────────────────────────────────────────────────────

    def _wait_for_dir(self, backup_session_data: BackupSessionPromptDTO) -> None:
        # ── Wait for the user to pick a destination folder ────────────────────
        self._dest_event.wait(timeout=120)

        if self._cancel_event.is_set() or self._dest_dir is None:
            return
        dest_dir: Path = self._dest_dir
        if self._is_running.is_set():
            self._executor.submit(self._notify_ready, dest_dir)

    def _notify_ready(self, dest_dir: Path) -> None:
        # ── Send ready ack to Android ─────────────────────────────────────────
        tau = self._connectivity.tau
        try:
            network.write_string_to_channel(tau, BackupChannels.BACKUP_READY_FROM_PC.value, "ready")
        except Exception as exc:
            logger.error("Failed to send ready ack: %s", exc)
            return

        if self._is_running.is_set():
            self._executor.submit(self._listen_android_controls)
            self._executor.submit(self._get_files, dest_dir)

    def _get_files(self, dest_dir: Path) -> None:
        # Poll get_peer_waiting_words() until all expected slots have been opened
        # by Android, spawning exactly one _receive_file thread per slot. Wait for
        # every slot to reach a terminal state before emitting backup_complete and
        # cleaning up the temp cache.
        dest_dir.mkdir(parents=True, exist_ok=True)
        cache_dir: Path = Path(tempfile.mkdtemp(prefix="SyncDose_backup_"))

        try:
            if self._file_count is None:
                return
            file_count: int = self._file_count

            slot_events: list[threading.Event] = [
                threading.Event() for _ in range(file_count)
            ]

            classifier: Classifier = Classifier(cache_dir / "classify.db")

            # Track which channels have already been dispatched so polling the same
            # open channels multiple times never double-spawns a slot.
            spawned_channels: set[str] = set()
            count: int = 0

            # ── Stall detection ────────────────────────────────────────────────
            # Mutable cells (list wrappers) let the _tracked_slot closure mutate
            # them without nonlocal rebinding.
            # _active[0]  — number of _receive_file tasks currently running.
            # _last_t[0]  — monotonic timestamp of the last dispatch or slot finish.
            # Both are updated under _stall_lock for cross-thread safety.
            _active: list[int] = [0]
            _last_t: list[float] = [time.monotonic()]
            _stall_lock: threading.Lock = threading.Lock()

            def _tracked_slot(
                mc: str,
                dc: Path,
                cd: Path,
                evt: threading.Event,
                clf: Classifier,
            ) -> None:
                # Thin wrapper: runs _receive_file then marks the slot as done
                # so the stall detector knows no worker is active and resets
                # the idle clock, giving Android a fresh grace window for the
                # next slot.
                try:
                    self._receive_file(mc, dc, cd, evt, clf)
                finally:
                    with _stall_lock:
                        _active[0] -= 1
                        _last_t[0] = time.monotonic()

            while count < file_count:
                if self._cancel_event.is_set():
                    # Signal remaining (unspawned) events so the wait loop below
                    # doesn't hang when the session is canceled mid-discovery.
                    for i in range(count, file_count):
                        slot_events[i].set()
                    break

                # Don't dispatch new slots while paused — in-flight slots (already
                # spawned) drain to completion via their own pause checks.
                while self._pause_event.is_set() and not self._cancel_event.is_set():
                    time.sleep(0.5)
                if self._cancel_event.is_set():
                    for i in range(count, file_count):
                        slot_events[i].set()
                    break

                open_channels: list[str] = self._connectivity.tau.get_peer_waiting_words()
                for c in open_channels:
                    if (
                            c.startswith(BackupChannels.BACKUP_FILE_META_SLOT.value)
                            and c not in spawned_channels
                            and count < file_count
                    ):
                        spawned_channels.add(c)
                        with _stall_lock:
                            _active[0] += 1
                            _last_t[0] = time.monotonic()
                        self._slot_executor.submit(
                            _tracked_slot, c, dest_dir, cache_dir, slot_events[count], classifier
                        )
                        count += 1

                if count < file_count:
                    # ── Stall check ────────────────────────────────────────────
                    # Trigger only when ALL workers are idle (active == 0).
                    # A non-zero active count means transfers are in progress —
                    # slow but not stalled; each slot already has its own
                    # _data_timeout to handle a stuck channel read.
                    with _stall_lock:
                        currently_active: int = _active[0]
                        elapsed_idle: float = time.monotonic() - _last_t[0]
                    if currently_active == 0 and elapsed_idle > _STALL_TIMEOUT_S:
                        self.backup_error.emit(
                            f"Backup stalled — no activity for {int(elapsed_idle)} s"
                        )
                        self._cancel_event.set()
                        for i in range(count, file_count):
                            slot_events[i].set()
                        break
                    # Yield the GIL briefly so spawned threads can run, and so we
                    # don't busy-spin waiting for Android to open more threads.
                    time.sleep(0.05)

            # ── Wait for every slot to finish (or session cancelled) ─────────────
            for evt in slot_events:
                while not evt.wait(timeout=1.0):
                    if self._cancel_event.is_set():
                        break
        finally:
            # Always wipe the temp cache — individual slot files are already
            # removed by _receive_file, but this catches any stragglers left
            # by an early return or an unexpected exception mid-session.
            shutil.rmtree(cache_dir, ignore_errors=True)

        self.backup_complete.emit()

    @staticmethod
    def _get_file_metadata(stream: TauSyncStream) -> tuple[str, int, int, Path | None, int]:
        # Read the newline-terminated JSON metadata line that Android sends
        # before the raw file bytes, and return (name, size_bytes, mtime_epoch,
        # rel_path, orig_size_bytes).  rel_path is None when the sender omits
        # the field.  orig_size_bytes equals size_bytes when Android omits
        # "orig_size" (non-storage-saver sessions or raw-fallback slots).
        meta_line: bytes = stream.read_line()
        meta: dict[str, Any] = json.loads(meta_line.decode("utf-8").strip())
        file_name: str = meta["name"]
        size_bytes: int = int(meta["size"])
        # Original modification time from the phone (epoch milliseconds); applied
        # via os.utime (converted to seconds) after the file is copied to
        # preserve the phone's mtime.
        mtime: int = int(meta.get("mtime", 0))
        # Original (pre-compression) size sent by Android when Storage Saver
        # re-encoded the file.  Defaults to size_bytes so the ViewModel computes
        # zero savings and leaves _total_bytes unchanged for non-compressed files.
        orig_size_bytes: int = int(meta.get("orig_size", size_bytes))
        rel_path_str: str | None = meta.get("rel_path", None)
        rel_path: Path | None = Path(rel_path_str) if rel_path_str is not None else None

        return file_name, size_bytes, mtime, rel_path, orig_size_bytes

    def _download_file_to_cache(self, stream: TauSyncStream, cache_dest: Path,
                                file_name: str, file_size: int) -> None:
        # Pause and cancel are NOT checked inside this loop — interrupting a live
        # TauSync stream mid-read stalls Android's write side until its channel
        # timeout fires, corrupting the session.  The gate in _receive_file
        # (before tau.connect is called) is the correct place to honour
        # pause/cancel; once the data channel is open we must drain it fully.
        bytes_read = 0
        t1_start = time.monotonic()
        chunk_size: int = 65536  # 64 KB — matches TauSync SDK default; 64× fewer CLR crossings
        last_emit_t: float = 0.0

        with open(cache_dest, "wb") as f:
            while bytes_read < file_size:
                to_read = min(chunk_size, file_size - bytes_read)
                chunk = stream.read(to_read)
                if not chunk:
                    break
                f.write(chunk)
                bytes_read += len(chunk)

                # Rate-limit to 5 Hz per slot — a 50 MB file at 64 KB chunks
                # would otherwise fire ~800 queued cross-thread signal emissions.
                now = time.monotonic()
                if now - last_emit_t >= 0.2:
                    elapsed = now - t1_start
                    speed_bps = bytes_read / elapsed if elapsed > 0 else 0.0
                    virtual_done = bytes_read // 2
                    self.file_progress.emit(file_name, virtual_done, speed_bps)
                    last_emit_t = now

    def _finish(self, succeeded: bool, result_channel: str, file_name: str,
                finished_event: threading.Event, reason: str | None = None,
                *, local_skipped: bool = False, dest_path: Path | None = None) -> None:
        # Report this slot's terminal state to the ViewModel and to Android.
        #
        # succeeded=True  + local_skipped=False → file_complete  (saved OK)
        # succeeded=True  + local_skipped=True  → file_skipped   (transfer OK, not kept;
        #                                          Android still gets SUCCESS)
        # succeeded=False                        → file_failed    (transport / IO error;
        #                                          Android gets FAILURE)
        if succeeded:
            if local_skipped:
                self.file_skipped.emit(file_name)
            else:
                # Include the absolute on-disk path so the UI can load a thumbnail.
                self.file_complete.emit(file_name, str(dest_path) if dest_path else "")
            result = BackupFileResult.SUCCESS
        else:
            self.file_failed.emit(file_name, reason or "unknown error")
            result = BackupFileResult.FAILURE

        tau = self._connectivity.tau

        try:
            # 30 s is well above the ~2 s Android result-handler polling cycle.
            # Without a timeout, _finish blocks indefinitely if Android never
            # opens the result channel (e.g. metaSent=false path on Android),
            # which prevents finished_event from being set and hangs backup_complete.
            network.write_string_to_channel(tau, result_channel, result.value, timeout_seconds=30)
        except Exception as exc:
            logger.error("Failed to send transfer result on %s: %s", result_channel, exc)

        finished_event.set()

    def _handle_post_copy_review(
            self,
            channel: str,
            dest_path: Path,
            file_name: str,
            confidence: float,
    ) -> None:
        # Run the NEEDS_REVIEW prompt *after* the file has already been saved.
        # Spawned immediately after _finish for the owning slot, so the
        # coordinator and Android are never kept waiting on the user's decision.
        # If discarded (by the user or a cancelled session), remove the
        # already-saved copy at dest_path and emit file_skipped so the ViewModel
        # can flip the file's status even though the slot already finished.
        keep = self._await_review_decision(channel, file_name, dest_path, confidence)
        if self._cancel_event.is_set():
            return
        if not keep:
            dest_path.unlink(missing_ok=True)
            self.file_skipped.emit(file_name)

    def _receive_file(
            self,
            meta_channel: str,
            dest_dir: Path,
            cache_dir: Path,
            finished_event: threading.Event,
            classifier: Classifier
    ) -> None:
        # Receive, screen, and save a single backup slot.
        #
        # The slot is split across two TauSync channels:
        #   • meta_channel  (backup_slot_meta_N) — JSON metadata only; short fixed timeout.
        #   • data_channel  (backup_slot_data_N) — raw bytes only; file-size-proportional
        #     timeout computed *after* the metadata is read so we know the file size.
        #
        # Always calls finished_event.set() before returning — success, failure, or
        # cancellation — so _get_files is never left waiting.  For every non-cancelled
        # terminal state also writes a BackupFileResult token on backup_file_result_{i}.
        # ── Pause / cancel check ──────────────────────────────────────────────
        while self._pause_event.is_set():
            if self._cancel_event.is_set():
                finished_event.set()
                return
            time.sleep(0.5)
        if self._cancel_event.is_set():
            return

        tau = self._connectivity.tau

        # Derive sibling channels from the meta channel name.
        channel_suffix: str = meta_channel.removeprefix(BackupChannels.BACKUP_FILE_META_SLOT.value)
        data_channel: str = BackupChannels.BACKUP_FILE_DATA_SLOT.value + channel_suffix
        result_channel: str = BackupChannels.BACKUP_FILE_RESULT.value + channel_suffix

        file_name: str = ""
        rel_path: Path | None = None

        # ── 1. Metadata — short fixed connect timeout ─────────────────────────
        # The meta channel carries only a tiny JSON object; 60 s is a generous
        # budget that covers slow connections and temporary Android pauses —
        # Android opens this channel immediately after the pause/cancel check above.
        try:
            with tau.connect(meta_channel, timeout_seconds=60) as meta_stream:
                file_name, file_size, mtime, rel_path, orig_size = self._get_file_metadata(meta_stream)
        except Exception as exc:
            logger.error("Slot %s metadata error: %s", meta_channel, exc)
            self._finish(False, result_channel, file_name, finished_event, f"Metadata error: {exc}")
            return

        self.file_registered.emit(file_name, file_size, orig_size)
        self.file_progress.emit(file_name, 0, 0.0)
        # UUID-based ASCII cache filename — keeps C# interop happy with any
        # Unicode characters in the original Android filename.
        cache_path = cache_dir / f"{uuid.uuid4().hex}{Path(file_name).suffix}"

        # ── 2. File bytes — file-size-proportional connect timeout ────────────
        # Now that file_size is known we can set a timeout that scales with the
        # expected transfer duration instead of a one-size-fits-all value.
        try:
            with tau.connect(data_channel, timeout_seconds=self._data_timeout(file_size)) as data_stream:
                self._download_file_to_cache(data_stream, cache_path, file_name, file_size)
        except Exception as exc:
            logger.error("Slot %s transport error: %s", data_channel, exc)
            if cache_path is not None:
                cache_path.unlink(missing_ok=True)
            self._finish(False, result_channel, file_name, finished_event, f"Transport error: {exc}")
            return

        if self._cancel_event.is_set():
            cache_path.unlink(missing_ok=True)
            finished_event.set()
            return

        # ── Compute destination path ──────────────────────────────────────────
        # Folder-mode backups (rel_path is not None) mirror the original
        # directory structure under dest_dir.  All-media backups (rel_path is
        # None) are organized into photos/{year}/{MM-MonthName}/ or
        # videos/{year}/{MM-MonthName}/ subdirectories derived from the file's
        # extension and modification time.
        if rel_path is not None:
            dest_path: Path = dest_dir / rel_path
        else:
            dest_path = dest_dir / BackupService._media_subdir(file_name, mtime)
        # The relative path may contain subdirectories that don't exist yet
        # inside dest_dir — create them before copying.
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        # ── Deduplicate destination filename ─────────────────────────────────
        # Avoid silently overwriting a file from a previous backup of the same
        # directory — append a counter suffix until the name is free.
        dest_path = self._unique_dest(dest_path)

        # ── Screen the cached file ────────────────────────────────────────────
        outcome: ClassificationResult = classifier.classify(cache_path, dest_path, use_ml=self._classify)

        if outcome.verdict is ClassificationVerdict.REJECTED:
            # PC-local screening rejected this file (duplicate, or confidently
            # filtered by the ML classifier). The transfer completed — Android
            # gets SUCCESS — but the file is not kept locally.
            cache_path.unlink(missing_ok=True)
            self._finish(True, result_channel, file_name, finished_event, local_skipped=True)
            return

        # ── Accepted (or pending review) — save to dest_dir ───────────────────
        # _copy_from_cache returns False when _cancel_event fires mid-copy; in
        # that case the partial dest_path write has already been cleaned up
        # inside the method and finished_event has been set — just exit.
        if not self._copy_from_cache(cache_path, dest_path, finished_event, file_size, file_name):
            cache_path.unlink(missing_ok=True)
            return

        # Restore the phone's original mtime on the saved file so the backup
        # reflects when the file was actually created/modified on the device,
        # not when it was transferred.
        if mtime:
            mtime_s: float = mtime / 1000.0
            os.utime(dest_path, (mtime_s, mtime_s))

        cache_path.unlink(missing_ok=True)

        # Report the slot as done *now* — the optional NEEDS_REVIEW prompt
        # below runs asynchronously and must never delay finished_event/Android.
        # Pass dest_path (already unique-renamed) so the UI can load a thumbnail.
        self._finish(True, result_channel, file_name, finished_event, "Success",
                     dest_path=dest_path)

        if outcome.verdict is ClassificationVerdict.NEEDS_REVIEW:
            if self._is_running.is_set():
                self._executor.submit(
                    self._handle_post_copy_review,
                    meta_channel, dest_path, file_name, outcome.confidence,
                )

    def _await_review_decision(
            self,
            channel: str,
            file_name: str,
            file_path: Path,
            confidence: float,
    ) -> bool:
        # Emit review_required with a BackupReviewPromptDTO (file_path reused as
        # the DTO's cache_path field for the preview thumbnail), then wait in
        # short increments — checking _cancel_event between each — until
        # resolve_review is called for channel or the session is canceled.
        # Returns True if the user chose to keep the file, False if discarded
        # or the session was canceled while waiting.
        decision_event = threading.Event()
        with self._review_lock:
            self._pending_reviews[channel] = decision_event

        self.review_required.emit(
            BackupReviewPromptDTO(
                channel=channel,
                file_name=file_name,
                cache_path=str(file_path),
                confidence=confidence,
            )
        )

        while not decision_event.wait(timeout=0.5):
            if self._cancel_event.is_set():
                break

        with self._review_lock:
            self._pending_reviews.pop(channel, None)
            keep = self._review_decisions.pop(channel, False)

        if self._cancel_event.is_set():
            return False
        return keep

    @staticmethod
    def _media_subdir(file_name: str, mtime_ms: int) -> Path:
        """Return the organized relative path for an all-media backup file.

        Determines whether the file is a photo or video from its extension and
        derives the year/month bucket from *mtime_ms*.  Unknown extensions fall
        back to a flat path (bare filename, no subdirectory prefix).

        Directory hierarchy::

            photos|videos / YYYY / MM-MonthName / file_name

        Example: ``"IMG_001.jpg"`` with mtime 2024-03-15
        → ``photos/2024/03-March/IMG_001.jpg``

        Args:
            file_name: Bare filename including extension (e.g. ``"IMG_001.jpg"``).
            mtime_ms:  Last-modified time in milliseconds since epoch, as sent by
                       Android in the per-slot JSON metadata ``"mtime"`` field.
                       Defaults to ``0`` (epoch) when the sender omits the field,
                       producing a ``…/1970/01-January/`` bucket.

        Returns:
            A :class:`~pathlib.Path` relative to the user-chosen destination
            directory.
        """
        ext = Path(file_name).suffix.lstrip(".").lower()
        if ext in _PHOTO_EXTENSIONS:
            media_dir = "photos"
        elif ext in _VIDEO_EXTENSIONS:
            media_dir = "videos"
        else:
            # Unknown media type — save flat inside dest_dir with no subdirectory.
            return Path(file_name)

        dt = datetime.fromtimestamp(mtime_ms / 1000)
        month_dir = f"{dt.strftime('%m')}-{dt.strftime('%B')}"  # e.g. "03-March"
        return Path(media_dir) / str(dt.year) / month_dir / file_name

    @staticmethod
    def _unique_dest(dest_path: Path) -> Path:
        # If dest_path already exists, append a counter suffix before the
        # extension until a free name is found.  Prevents silently overwriting
        # files saved during a previous backup of the same source directory.
        if not dest_path.exists():
            return dest_path
        stem = dest_path.stem
        suffix = dest_path.suffix
        parent = dest_path.parent
        counter = 1
        while True:
            candidate = parent / f"{stem} ({counter}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _copy_from_cache(self, cache_path: Path, dest_path: Path, finished_event: threading.Event,
                         file_size: int, file_name: str, chunk_size: int = 65536) -> bool:
        # Copy cache_path → dest_path in chunks, emitting file_progress at most
        # 5 Hz.  Returns True when the copy completes normally.  Returns False
        # when _cancel_event fires mid-copy — in that case the partial dest_path
        # write is cleaned up here and finished_event is set before returning so
        # _get_files is never left waiting; the caller must exit without calling
        # _finish (no slot result token should be sent for a cancelled slot).
        phase1_virtual_end = file_size // 2
        bytes_copied = 0
        t2_start = time.monotonic()
        last_emit_t: float = 0.0
        with open(cache_path, "rb") as src, open(dest_path, "wb") as dst:
            while True:
                if self._cancel_event.is_set():
                    dest_path.unlink(missing_ok=True)  # remove the partial write
                    finished_event.set()
                    return False
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                dst.write(chunk)
                bytes_copied += len(chunk)

                now = time.monotonic()
                if now - last_emit_t >= 0.2:
                    elapsed = now - t2_start
                    speed_bps = bytes_copied / elapsed if elapsed > 0 else 0.0
                    virtual_done = phase1_virtual_end + bytes_copied // 2
                    self.file_progress.emit(file_name, virtual_done, speed_bps)
                    last_emit_t = now
        shutil.copystat(str(cache_path), str(dest_path))
        return True

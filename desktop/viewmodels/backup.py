from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from domain.dto.backup_review_prompt import BackupReviewPromptDTO
from domain.enums.backup_status import BackupStatus
from services.backup import BackupService
from services.connectivity import ConnectivityService


class BackupViewModel(QObject):
    """ViewModel for the backup progress screen.

    Tracks per-file status and byte progress for the current backup session
    and exposes the results as Signals.  The view layer connects to these
    signals and updates its own widgets in response — the ViewModel never
    touches view objects directly.

    Architecture notes:
        * The view **never** imports from services or repositories.  It wires
          itself to this ViewModel's signals and calls the ViewModel's public
          methods in response to user actions (confirm destination, cancel,
          pause, resume).
        * When Android sends a backup manifest the service emits
          ``manifest_received`` with a
          :class:`~domain.dto.backup_session_prompt.BackupSessionPromptDTO`.
          The ViewModel resets its session state and emits
          ``dest_dir_requested`` so the view can open a folder-picker dialog.
        * Per-file state (``_statuses``, ``_bytes_done_map``, ``_file_sizes``)
          is **lazily initialised** via :attr:`file_registered` signals
          emitted by the service when each slot's JSON header is read.  This
          is necessary because the manifest only contains the total file count
          and size — not per-file metadata.
        * The view calls :meth:`confirm_dest_dir` (user picked a folder) or
          :meth:`cancel_dest_selection` (user dismissed the picker).  Both are
          **not** gated by connectivity so the user can always dismiss an
          incoming request.
        * Pause, resume, and cancel are **not** gated — an in-flight session
          must remain controllable even after a disconnect.

    Flow::

        Android sends manifest
          → service.manifest_received(prompt)
          → _on_manifest_received  (resets state, emits dest_dir_requested)
          → view opens QFileDialog
          → user picks folder  → confirm_dest_dir(path) → service.proceed(path)
          → user cancels       → cancel_dest_selection() → service.cancel_session()

        After proceed():
          → service sends "ready" to Android
          → For each slot i:
                service emits file_registered(rel_path, size_bytes)
                  → VM initialises _statuses / _bytes_done_map / _file_sizes
                service emits file_progress(rel_path, bytes, speed)
                (if classifier returns NEEDS_REVIEW:
                    service emits review_required(BackupReviewPromptDTO)
                      → _on_review_required
                          → service.resolve_review(channel, keep=True)  ← unblocks thread immediately
                          → _review_flagged.append(prompt)              ← accumulates for post-session review)
                service emits file_complete(rel_path) | file_failed(rel_path, reason)
          → service emits backup_complete

    Signals:
        dest_dir_requested (Signal[object]): Emitted with a
            :class:`~domain.dto.backup_session_prompt.BackupSessionPromptDTO`
            when a manifest arrives from Android.  The view should open a
            folder-picker dialog and call :meth:`confirm_dest_dir` or
            :meth:`cancel_dest_selection` in response.
        backup_ready (Signal[int, int]): Emitted as ``(file_count, total_bytes)``
            once the user confirms a destination so the view can open/reset
            the progress window.
        file_registered (Signal[str, int]): Forwarded from the service as
            ``(rel_path, size_bytes)`` when each slot's JSON header is parsed.
            The view uses this to lazily create per-file row widgets before any
            progress ticks arrive.
        file_progress_updated (Signal[str, int, float]): Emitted on every
            progress tick as ``(rel_path, bytes_done, speed_bps)``.
        file_status_changed (Signal[str, object]): Emitted on every status
            transition as ``(rel_path, BackupStatus)``.
        overall_updated (Signal[int, int, float]): Emitted after every progress
            tick as ``(total_bytes, done_bytes, eta_secs)``.  ``eta_secs`` is
            ``-1.0`` when not yet computable.
        backup_complete (Signal): Emitted once every file reaches ``DONE``,
            ``FAILED``, or ``SKIPPED``.
        backup_error (Signal[str]): Emitted on a session-level error.
        device_ready_changed (Signal[bool]): ``True`` when a device connects,
            ``False`` when it disconnects.
        review_requested (Signal[object]): Reserved — not currently emitted.
            ML-flagged files are auto-kept during the session and accumulated in
            ``_review_flagged``; the batch review dialog is driven by
            :attr:`backup_session_result` after the session completes.
    """

    # ── Signals ───────────────────────────────────────────────────────────────

    dest_dir_requested: Signal = Signal(int, 'qint64', bool)  # (file_count, total_bytes, storage_saver)
    backup_ready: Signal = Signal(int, 'qint64')        # (file_count, total_bytes)
    file_registered: Signal = Signal(str, 'qint64')     # (rel_path, size_bytes)
    file_progress_updated: Signal = Signal(str, 'qint64', float)
    file_status_changed: Signal = Signal(str, object)
    file_saved_at: Signal = Signal(str, str)             # (file_name, abs_dest_path) — images only thumbnail hint
    overall_updated: Signal = Signal('qint64', 'qint64', float)  # (total_bytes, done_bytes, eta_secs)
    backup_complete: Signal = Signal()
    backup_error: Signal = Signal(str)
    device_ready_changed: Signal = Signal(bool)
    pause_state_changed: Signal = Signal(bool)  # True = paused, False = resumed
    review_requested: Signal = Signal(object)  # BackupReviewPromptDTO
    backup_session_result: Signal = Signal(list, str)  # (flagged_prompts: list[BackupReviewPromptDTO], dest_dir) — fires after backup_complete

    def __init__(
            self,
            backup_service: BackupService,
            connectivity_service: ConnectivityService,
            parent: QObject | None = None,
    ) -> None:
        """Wire service signals and initialise empty session state.

        Args:
            backup_service: The service that manages Android-to-PC transfers
                and emits per-file progress / completion events.
            connectivity_service: Used to track device connectivity and emit
                :attr:`device_ready_changed`.
            parent: Optional Qt parent for memory management.
        """
        super().__init__(parent)

        self._backup_service: BackupService = backup_service
        self._connectivity_service: ConnectivityService = connectivity_service

        # ── Session state ─────────────────────────────────────────────────────
        self._file_count: int = 0
        self._statuses: dict[str, BackupStatus] = {}
        self._bytes_done_map: dict[str, int] = {}
        self._file_sizes: dict[str, int] = {}  # rel_path → expected total bytes
        self._total_bytes: int = 0
        self._done_bytes: int = 0
        self._session_start_time: float | None = None
        self._is_paused: bool = False
        self._is_device_connected: bool = False
        self._is_active: bool = False
        self._classify: bool = False        # forwarded from BackupSessionPromptDTO.classify
        self._storage_saver: bool = False   # forwarded from BackupSessionPromptDTO.storage_saver
        self._effective_total_bytes: int = 0  # running sum of per-slot meta["size"] (re-encoded sizes)
        self._dest_dir: str = ""            # path chosen by the user; used in backup_session_result
        self._review_flagged: list[BackupReviewPromptDTO] = []  # ML-flagged files accumulated during session

        # ── Connectivity wiring ───────────────────────────────────────────────
        self._connectivity_service.device_connected.connect(self._on_device_connected)
        self._connectivity_service.device_disconnected.connect(self._on_device_disconnected)

        # ── BackupService wiring ──────────────────────────────────────────────
        self._backup_service.manifest_received.connect(self._on_manifest_received)
        self._backup_service.file_registered.connect(self._on_file_registered)
        self._backup_service.file_progress.connect(self._on_file_progress)
        self._backup_service.file_complete.connect(self._on_file_complete)
        self._backup_service.file_failed.connect(self._on_file_failed)
        self._backup_service.file_skipped.connect(self._on_file_skipped)
        self._backup_service.backup_complete.connect(self._on_backup_complete)
        self._backup_service.backup_error.connect(self.backup_error)
        self._backup_service.session_paused.connect(self._on_session_paused)
        self._backup_service.session_resumed.connect(self._on_session_resumed)
        self._backup_service.review_required.connect(self._on_review_required)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def device_connected(self) -> bool:
        """Whether a device is currently connected."""
        return self._is_device_connected

    @property
    def is_active(self) -> bool:
        """Whether a backup session is currently in progress."""
        return self._is_active

    def confirm_dest_dir(self, dest_dir: str) -> None:
        """User confirmed a backup destination folder — unblock the service.

        Called by the view after the user picks a folder in the
        ``dest_dir_requested`` dialog.  Emits :attr:`backup_ready` with the
        session's file count and total byte size so the view can open the
        progress window.

        Guards against the race where the device disconnects while the folder
        picker is open: ``_on_device_disconnected`` resets ``_is_active`` via
        :meth:`cancel`, so a stale "Accept" click after disconnect is a no-op.

        Args:
            dest_dir: Absolute path to the chosen backup folder.
        """
        if not self._is_active:
            # Session was cancelled (e.g. device disconnected) before the user
            # responded — nothing to proceed with.
            return
        self._dest_dir = dest_dir
        self.backup_ready.emit(self._file_count, self._total_bytes)
        self._backup_service.proceed(Path(dest_dir))

    def cancel_dest_selection(self) -> None:
        """User dismissed the folder picker — abort the pending backup session.

        Not gated by connectivity.
        """
        self._backup_service.cancel_session()
        self._reset_session()

    def pause(self) -> None:
        """Pause all active transfers.

        Not gated by connectivity — in-flight transfers must be pausable even
        if the device disconnects mid-session.
        """
        if not self._is_active or self._is_paused:
            return
        self._is_paused = True
        self._backup_service.pause()

    def resume(self) -> None:
        """Resume all paused transfers.

        Not gated by connectivity.
        """
        if not self._is_active or not self._is_paused:
            return
        self._is_paused = False
        self._backup_service.resume()

    def cancel(self) -> None:
        """Cancel the running backup session and reset internal state.

        Works during both the destination-picker phase and the active transfer
        phase.  Not gated by connectivity.
        """
        if not self._is_active:
            return
        self._backup_service.cancel()
        self._reset_session()

    def resolve_review(self, channel: str, keep: bool) -> None:
        """User responded to a pending confidence review prompt.

        Called by the view after the user dismisses the dialog shown for
        :attr:`review_requested`. Not gated by connectivity — the user must
        be able to respond even if the device disconnects mid-session.

        Args:
            channel: The slot channel from the originating
                :class:`~domain.dto.backup_review_prompt.BackupReviewPromptDTO`.
            keep: ``True`` to keep the file, ``False`` to discard it.
        """
        self._backup_service.resolve_review(channel, keep)

    # ── Connectivity slots ────────────────────────────────────────────────────

    @Slot()
    def _on_device_connected(self) -> None:
        """Notify the view that a device is connected."""
        self._is_device_connected = True
        self.device_ready_changed.emit(True)

    @Slot()
    def _on_device_disconnected(self) -> None:
        """Notify the view that the device has disconnected.

        If a backup session is in progress it is cancelled automatically —
        the phone is gone so there is nothing left to transfer from.
        The service-side threads are already being torn down by
        ``AppState``'s ``backup_service.stop()`` wiring; this call resets
        the ViewModel state and lets the view close the progress window.
        """
        self._is_device_connected = False
        # Auto-cancel any in-progress session so _reset_session() fires and
        # the view receives device_ready_changed(False) with _is_active=False.
        if self._is_active:
            self.cancel()
        self.device_ready_changed.emit(False)

    # ── BackupService slots ───────────────────────────────────────────────────

    @Slot(int, 'qint64', bool, bool)
    def _on_manifest_received(self, files_count: int, files_size: int,
                               classify: bool, storage_saver: bool) -> None:
        """Android sent a manifest header — reset session state and ask for dest.

        Sets ``_is_active = True`` immediately so :meth:`cancel` works during
        the folder-picker phase.

        Args:
            files_count:   Total number of files in the incoming session.
            files_size:    Total byte size of all files (original sizes, upper bound).
            classify:      Whether the session will run ML content screening.
            storage_saver: Whether Android will re-encode images before sending.
                           When ``True``, actual bytes transferred < ``files_size``.
        """
        if self._is_active:
            # A session is already running — ignore the incoming manifest.
            return

        self._reset_session(
            file_count=files_count,
            total_bytes=files_size,
        )
        self._classify = classify
        self._storage_saver = storage_saver
        self._is_active = True
        self.dest_dir_requested.emit(files_count, files_size, storage_saver)

    @Slot(str, 'qint64', 'qint64')
    def _on_file_registered(self, rel_path: str, size_bytes: int, orig_size_bytes: int) -> None:
        """Lazily initialise per-file tracking state when a slot header arrives.

        Called by the service after reading each slot's JSON metadata line,
        before any progress ticks are emitted for that file.  Forwards the
        event to the view layer via :attr:`file_registered` so the view can
        create its per-file row widget.

        When Storage Saver is active and Android re-encoded this file,
        ``orig_size_bytes > size_bytes``.  The difference (the byte savings)
        is subtracted from ``_total_bytes`` so the overall progress denominator
        converges from the manifest's original-size total toward the exact
        compressed total as slots register.  Because ``size_bytes ≤ orig_size_bytes``
        the denominator can only decrease — the progress bar never jumps backward.

        Args:
            rel_path:       File name / relative path used as the per-file key.
            size_bytes:     Actual (compressed) byte count for this file.
            orig_size_bytes: Original (pre-compression) byte count as reported
                            by Android.  Equals ``size_bytes`` for non-compressed
                            files (raw fallback or non-media), producing zero savings.
        """
        self._statuses[rel_path] = BackupStatus.QUEUED
        self._bytes_done_map[rel_path] = 0
        self._file_sizes[rel_path] = size_bytes
        self._effective_total_bytes += size_bytes

        # Progressively correct the running total when Storage Saver compressed
        # this file.  The manifest counted orig_size_bytes but only size_bytes will
        # actually be transferred — subtract the savings so _total_bytes (denominator)
        # converges to the real compressed total without ever increasing.
        if self._storage_saver:
            savings = orig_size_bytes - size_bytes
            if savings > 0:
                self._total_bytes = max(0, self._total_bytes - savings)

        self.file_registered.emit(rel_path, size_bytes)  # VM's own signal stays (str, qint64)
        self._transition_status(rel_path, BackupStatus.QUEUED)

    @Slot(str, 'qint64', float)
    def _on_file_progress(self, path: str, bytes_done: int, speed_bps: float) -> None:
        """Handle a per-file progress tick from the backup service.

        Updates internal byte counters, transitions the file to ``ACTIVE`` on
        first tick, and emits :attr:`file_progress_updated` and
        :attr:`overall_updated`.

        Args:
            path:       ``rel_path`` key identifying the file.
            bytes_done: Number of bytes received so far.
            speed_bps:  Current transfer speed in bytes per second.
        """
        if path not in self._bytes_done_map:
            return

        previous = self._bytes_done_map[path]
        self._bytes_done_map[path] = bytes_done
        self._done_bytes = max(0, self._done_bytes + (bytes_done - previous))

        if self._session_start_time is None and bytes_done > 0:
            self._session_start_time = time.monotonic()

        if self._statuses.get(path) != BackupStatus.ACTIVE:
            self._transition_status(path, BackupStatus.ACTIVE)

        self.file_progress_updated.emit(path, bytes_done, speed_bps)
        self.overall_updated.emit(self._progress_total, self._done_bytes, self._compute_eta())

    @Slot(str, str)
    def _on_file_complete(self, path: str, abs_dest_path: str) -> None:
        """Handle successful save of a single file.

        Marks the file ``DONE``, credits its full size to ``_done_bytes``, and
        checks whether the entire session is finished.  Emits
        :attr:`file_saved_at` with the absolute on-disk path so the UI can
        load a thumbnail for image files.

        Args:
            path:          ``file_name`` key of the completed file.
            abs_dest_path: Absolute filesystem path where the file was saved
                           (may be empty string if path was not available).
        """
        if path not in self._statuses:
            return

        file_size = self._file_sizes.get(path, 0)
        self._bytes_done_map[path] = file_size
        self._done_bytes = sum(self._bytes_done_map.values())

        self._transition_status(path, BackupStatus.DONE)
        self.overall_updated.emit(self._progress_total, self._done_bytes, self._compute_eta())
        if abs_dest_path:
            self.file_saved_at.emit(path, abs_dest_path)
        self._check_session_complete()

    @Slot(str, str)
    def _on_file_failed(self, path: str, error: str) -> None:  # noqa: ARG002
        """Handle a failed file (transport / IO error only).

        Marks the file ``FAILED``, credits its full byte size to
        ``_done_bytes`` (same as :meth:`_on_file_complete` and
        :meth:`_on_file_skipped`), and checks whether the session is
        finished.  Crediting the bytes prevents the overall progress bar
        from stalling and then abruptly jumping to 100 % when
        ``backup_complete`` fires.

        Args:
            path:  ``rel_path`` key of the failed file.
            error: Human-readable failure reason.
        """
        if path not in self._statuses:
            return

        # Credit the full file size so the progress bar advances smoothly.
        file_size = self._file_sizes.get(path, 0)
        self._bytes_done_map[path] = file_size
        self._done_bytes = sum(self._bytes_done_map.values())

        self._transition_status(path, BackupStatus.FAILED)
        self.overall_updated.emit(self._progress_total, self._done_bytes, self._compute_eta())
        self._check_session_complete()

    @Slot(str)
    def _on_file_skipped(self, path: str) -> None:
        """Handle a file that was not kept locally (auto-filtered or user-removed).

        The transfer completed and Android received ``SUCCESS`` — the file was
        simply not saved on the PC side.  Marks the file ``SKIPPED``, credits
        its full byte size to the overall progress (mirrors ``_on_file_complete``
        so the progress bar advances correctly), and checks whether the session
        is finished.

        Args:
            path: ``rel_path`` key of the skipped file.
        """
        if path not in self._statuses:
            return

        # Credit the full file size so the overall progress bar advances exactly
        # as it would for a saved file — the transfer completed successfully.
        file_size = self._file_sizes.get(path, 0)
        self._bytes_done_map[path] = file_size
        self._done_bytes = sum(self._bytes_done_map.values())

        self._transition_status(path, BackupStatus.SKIPPED)
        self.overall_updated.emit(self._progress_total, self._done_bytes, self._compute_eta())
        self._check_session_complete()

    @Slot()
    def _on_backup_complete(self) -> None:
        """Handle session-complete signal from the service.

        Guards against double-emission: :meth:`_check_session_complete` may
        have already fired :attr:`backup_complete` if all files reached a
        terminal state before this slot was delivered.
        """
        if not self._is_active:
            return  # already emitted via _check_session_complete
        self._is_active = False
        self._is_paused = False
        self.backup_complete.emit()
        self.backup_session_result.emit(self._review_flagged, self._dest_dir)

    @Slot()
    def _on_session_paused(self) -> None:
        """Android paused the transfer — sync local pause state and notify the view.

        Mirrors the bookkeeping in :meth:`pause` without re-sending a control
        command to Android (it already knows — it initiated this).
        """
        if self._is_paused:
            return
        self._is_paused = True
        self.pause_state_changed.emit(True)

    @Slot()
    def _on_session_resumed(self) -> None:
        """Android resumed the transfer — sync local pause state and notify the view."""
        if not self._is_paused:
            return
        self._is_paused = False
        self.pause_state_changed.emit(False)

    @Slot(object)
    def _on_review_required(self, prompt: BackupReviewPromptDTO) -> None:
        """Auto-keep a classifier-flagged file and accumulate it for post-session review.

        The service thread blocks until ``resolve_review`` is called, so we
        unblock it immediately with ``keep=True`` (the file is already saved to
        ``dest_dir``).  The prompt is added to ``_review_flagged`` so the full
        set of flagged files can be presented to the user in a single
        ``BackupReviewDialog`` after the session completes — rather than
        interrupting the transfer with per-file dialogs.

        Args:
            prompt: Describes the file awaiting a keep/discard decision.
        """
        self._backup_service.resolve_review(prompt.channel, True)
        self._review_flagged.append(prompt)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _reset_session(
            self,
            file_count: int = 0,
            total_bytes: int = 0,
    ) -> None:
        """Replace all session state with a fresh baseline.

        Per-file maps are cleared and will be lazily populated when
        :attr:`~services.backup.BackupService.file_registered` signals arrive.

        Args:
            file_count:   Number of files in the new session (0 to clear).
            total_bytes:  Total byte count for the new session (0 to clear).
        """
        self._file_count = file_count
        self._statuses = {}
        self._bytes_done_map = {}
        self._file_sizes = {}
        self._total_bytes = total_bytes
        self._effective_total_bytes = 0
        self._done_bytes = 0
        self._session_start_time = None
        self._is_paused = False
        self._is_active = False
        self._classify = False
        self._storage_saver = False
        self._dest_dir = ""
        self._review_flagged = []

    def _transition_status(self, path: str, status: BackupStatus) -> None:
        """Update the stored status for *path* and emit :attr:`file_status_changed`.

        Args:
            path:   ``rel_path`` key of the affected file.
            status: The new :class:`~domain.enums.backup_status.BackupStatus`.
        """
        self._statuses[path] = status
        self.file_status_changed.emit(path, status)

    def _check_session_complete(self) -> None:
        """Emit :attr:`backup_complete` if every registered file has reached
        a terminal state and all expected files have been registered.

        Emits only once — sets ``_is_active = False`` before emitting to
        prevent :meth:`_on_backup_complete` from double-firing.
        """
        # Guard: not all files have registered yet
        if len(self._statuses) < self._file_count:
            return

        terminal = {BackupStatus.DONE, BackupStatus.FAILED, BackupStatus.SKIPPED}
        if self._is_active and all(s in terminal for s in self._statuses.values()):
            self._is_active = False
            self._is_paused = False
            self.backup_complete.emit()
            self.backup_session_result.emit(self._review_flagged, self._dest_dir)

    @property
    def _progress_total(self) -> int:
        """Running total bytes used as the overall progress-bar and ETA denominator.

        Initialised to the manifest's ``_total_bytes`` (sum of original file sizes).
        When Storage Saver is active, :meth:`_on_file_registered` subtracts
        ``orig_size − compressed_size`` from ``_total_bytes`` for each slot that
        Android re-encoded.  Because ``compressed_size ≤ orig_size``, the denominator
        can only *decrease* — the progress bar never jumps backward.

        After all slots have registered, ``_total_bytes`` equals the exact sum of
        compressed sizes, so the bar reaches ≈ 100 % at session end without relying
        on the ``_on_backup_complete`` snap.

        Falls back to ``_effective_total_bytes`` only if the manifest total is
        unavailable (should not happen in practice).
        """
        return self._total_bytes or self._effective_total_bytes

    def _compute_eta(self) -> float:
        """Return estimated seconds remaining, or ``-1.0`` if not yet computable.

        Uses ``_progress_total`` (actual transferred sizes) rather than the
        manifest total so ETA is accurate when Storage Saver shrinks files.
        """
        if not self._session_start_time or self._done_bytes <= 0:
            return -1.0
        elapsed = time.monotonic() - self._session_start_time
        rate = self._done_bytes / elapsed  # bytes/sec
        remaining = max(0, self._progress_total - self._done_bytes)
        return remaining / rate if rate > 0 else -1.0

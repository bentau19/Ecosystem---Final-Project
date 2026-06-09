"""
ViewModel for the backup progress screen.

Owns all mutable state for an in-progress backup session — per-file status,
per-file byte counters, and the overall total — and translates that state into
PySide6 Signals that :class:`~views.widgets.backup.backup_progress_window.BackupProgressWindow`
(and any other subscriber) connects to.

Architecture notes
------------------
* The view **never** imports from services or repositories.  It wires itself
  to this ViewModel's signals and calls the ViewModel's public methods in
  response to user actions (pause, resume, cancel).
* ``start_backup`` is **gated** behind device connectivity — silently no-ops
  when no device is connected.
* Pause, resume, and cancel are **not** gated — an in-flight operation the
  user already confirmed must still be cancellable after a disconnect.

Service seam
------------
No ``BackupService`` exists yet.  The constructor accepts one via a
``TYPE_CHECKING``-guarded type annotation so the wiring is zero-cost at
runtime.  The private ``_on_*`` slots are fully implemented and ready to be
connected as soon as the service is built::

    backup_service.file_progress.connect(self._on_file_progress)
    backup_service.file_complete.connect(self._on_file_complete)
    backup_service.file_failed.connect(self._on_file_failed)
    backup_service.backup_complete.connect(self._on_backup_complete)

The ``BackupService`` will need to emit:

* ``file_progress(str, int, float)``  — (path, bytes_done, speed_bps)
* ``file_complete(str)``              — path
* ``file_failed(str, str)``           — (path, error_message)
* ``backup_complete()``
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from domain.dto.backup_file import BackupFileDTO
from domain.enums.backup_status import BackupStatus

if TYPE_CHECKING:
    from services.backup import BackupService
    from services.connectivity import ConnectivityService


class BackupViewModel(QObject):
    """ViewModel for the backup progress screen.

    Tracks per-file status and byte progress for the current backup session
    and exposes the results as Signals.  The view layer connects to these
    signals and updates its own widgets in response — the ViewModel never
    touches view objects directly.

    Signals:
        backup_ready (Signal[list]): Emitted with ``list[BackupFileDTO]`` when
            :meth:`start_backup` is called and the session is initialised.
            The view should create :class:`BackupProgressWindow` (or reset it)
            from this payload.
        file_progress_updated (Signal[str, int, float]): Emitted periodically
            during a transfer as ``(path, bytes_done, speed_bps)``.  Maps to
            ``BackupProgressWindow.update_progress``.
        file_status_changed (Signal[str, object]): Emitted on every status
            transition as ``(path, BackupStatus)``.  Maps to
            ``BackupProgressWindow.set_status``.
        overall_updated (Signal[int, int]): Emitted after every per-file
            progress tick as ``(total_bytes, done_bytes)``.  Maps to
            ``BackupProgressWindow.set_overall``.
        backup_complete (Signal): Emitted once every file reaches
            ``DONE`` or ``FAILED``.  Maps to ``BackupProgressWindow.mark_done``.
        backup_error (Signal[str]): Emitted when the service reports a
            session-level (non-file) error.
        device_ready_changed (Signal[bool]): ``True`` when a device connects,
            ``False`` when it disconnects — use this to enable/disable the
            "Start Backup" button.
    """

    # ── Signals ───────────────────────────────────────────────────────────────

    backup_ready: Signal            = Signal(list)          # list[BackupFileDTO]
    file_progress_updated: Signal   = Signal(str, int, float)  # path, bytes_done, speed_bps
    file_status_changed: Signal     = Signal(str, object)   # path, BackupStatus
    overall_updated: Signal         = Signal(int, int)      # total_bytes, done_bytes
    backup_complete: Signal         = Signal()
    backup_error: Signal            = Signal(str)
    device_ready_changed: Signal    = Signal(bool)

    def __init__(
            self,
            backup_service: BackupService,
            connectivity_service: ConnectivityService,
            parent: QObject | None = None,
    ) -> None:
        """Wire service signals and initialise empty session state.

        Args:
            backup_service: The service that performs the actual file I/O
                and emits per-file progress / completion events.
            connectivity_service: Used to gate :meth:`start_backup` and to
                forward ``device_ready_changed`` to the view.
            parent: Optional Qt parent for memory management.
        """
        super().__init__(parent)

        self._backup_service: BackupService = backup_service
        self._connectivity_service: ConnectivityService = connectivity_service

        # ── Session state ─────────────────────────────────────────────────────
        self._files: list[BackupFileDTO] = []
        self._statuses: dict[str, BackupStatus] = {}       # path → status
        self._bytes_done_map: dict[str, int] = {}          # path → bytes transferred
        self._total_bytes: int = 0
        self._done_bytes: int = 0
        self._is_paused: bool = False
        self._is_device_connected: bool = False
        self._is_active: bool = False

        # ── Connectivity wiring ───────────────────────────────────────────────
        self._connectivity_service.device_connected.connect(self._on_device_connected)
        self._connectivity_service.device_disconnected.connect(self._on_device_disconnected)

        # ── BackupService wiring ──────────────────────────────────────────────
        # Connect once BackupService is available; slots are fully implemented.
        #
        #   self._backup_service.file_progress.connect(self._on_file_progress)
        #   self._backup_service.file_complete.connect(self._on_file_complete)
        #   self._backup_service.file_failed.connect(self._on_file_failed)
        #   self._backup_service.backup_complete.connect(self._on_backup_complete)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def device_connected(self) -> bool:
        """Whether a device is currently connected."""
        return self._is_device_connected

    @property
    def is_active(self) -> bool:
        """Whether a backup session is currently in progress."""
        return self._is_active

    def start_backup(self, files: list[BackupFileDTO]) -> None:
        """Initialise a new backup session and begin transferring files.

        No-ops silently when no device is connected or when a session is
        already in progress.

        Emits:
            backup_ready: With the validated file list so the view can
                initialise (or reset) :class:`BackupProgressWindow`.

        Args:
            files: Ordered list of files to back up.  Empty lists are
                accepted and will immediately emit :attr:`backup_complete`.
        """
        if not self._is_device_connected or self._is_active:
            return

        self._reset_session(files)
        self.backup_ready.emit(list(self._files))

        if not self._files:
            # Nothing to do — complete immediately so the view reaches a
            # terminal state rather than waiting forever.
            self.backup_complete.emit()
            return

        self._is_active = True
        self._backup_service.start(paths=[f.path for f in self._files])

    def pause(self) -> None:
        """Pause all active transfers.

        Not gated by connectivity — in-flight transfers must be pausable
        even if the device disconnects mid-session.

        Emits nothing directly; the service will stop emitting
        ``file_progress`` events while paused.
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

        Not gated by connectivity — the user must always be able to cancel.
        """
        if not self._is_active:
            return
        self._backup_service.cancel()
        self._reset_session([])

    # ── Connectivity slots ────────────────────────────────────────────────────

    @Slot()
    def _on_device_connected(self) -> None:
        """Gate new backups and notify the view that the button can be enabled."""
        self._is_device_connected = True
        self.device_ready_changed.emit(True)

    @Slot()
    def _on_device_disconnected(self) -> None:
        """Drop the connectivity gate; leave any in-flight session untouched."""
        self._is_device_connected = False
        self.device_ready_changed.emit(False)

    # ── BackupService slots ───────────────────────────────────────────────────

    @Slot(str, int, float)
    def _on_file_progress(self, path: str, bytes_done: int, speed_bps: float) -> None:
        """Handle a per-file progress tick from the backup service.

        Updates internal byte counters, recomputes the overall total, and
        emits both :attr:`file_progress_updated` and :attr:`overall_updated`.

        Args:
            path: Absolute path of the file being transferred.
            bytes_done: Number of bytes transferred so far.
            speed_bps: Current transfer speed in bytes per second.
        """
        if path not in self._bytes_done_map:
            return

        previous = self._bytes_done_map[path]
        self._bytes_done_map[path] = bytes_done

        # Recompute overall done_bytes as a delta to avoid a full O(n) sum on
        # every tick.
        self._done_bytes = max(0, self._done_bytes + (bytes_done - previous))

        if self._statuses.get(path) != BackupStatus.ACTIVE:
            self._transition_status(path, BackupStatus.ACTIVE)

        self.file_progress_updated.emit(path, bytes_done, speed_bps)
        self.overall_updated.emit(self._total_bytes, self._done_bytes)

    @Slot(str)
    def _on_file_complete(self, path: str) -> None:
        """Handle successful completion of a single file transfer.

        Marks the file ``DONE``, credits its full size to ``done_bytes``,
        and checks whether the entire session is finished.

        Args:
            path: Absolute path of the completed file.
        """
        if path not in self._statuses:
            return

        file_size = next(
            (f.size_bytes for f in self._files if f.path == path), 0
        )
        self._bytes_done_map[path] = file_size
        self._done_bytes = sum(self._bytes_done_map.values())

        self._transition_status(path, BackupStatus.DONE)
        self.overall_updated.emit(self._total_bytes, self._done_bytes)
        self._check_session_complete()

    @Slot(str, str)
    def _on_file_failed(self, path: str, error: str) -> None:  # noqa: ARG002
        """Handle a failed file transfer.

        Marks the file ``FAILED`` and checks whether the session is finished.
        The per-file ``error`` string is absorbed here; session-level errors
        arrive via :meth:`_on_backup_error`.

        Args:
            path: Absolute path of the failed file.
            error: Human-readable error description (logged / future toast).
        """
        if path not in self._statuses:
            return

        self._transition_status(path, BackupStatus.FAILED)
        self._check_session_complete()

    @Slot()
    def _on_backup_complete(self) -> None:
        """Handle a session-complete event from the service.

        The service emits this after all file-level work is done.  The VM
        mirrors the check in :meth:`_check_session_complete` so either side
        can trigger the terminal state.
        """
        self._is_active = False
        self._is_paused = False
        self.backup_complete.emit()

    @Slot(str)
    def _on_backup_error(self, error: str) -> None:
        """Handle a session-level (non-file) error from the service.

        Args:
            error: Human-readable description of the session error.
        """
        self._is_active = False
        self._is_paused = False
        self.backup_error.emit(error)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _reset_session(self, files: list[BackupFileDTO]) -> None:
        """Replace all session state with a fresh baseline for *files*.

        Args:
            files: The new file list; pass ``[]`` to clear the session.
        """
        self._files = list(files)
        self._statuses = {f.path: BackupStatus.QUEUED for f in files}
        self._bytes_done_map = {f.path: 0 for f in files}
        self._total_bytes = sum(f.size_bytes for f in files)
        self._done_bytes = 0
        self._is_paused = False
        self._is_active = False

    def _transition_status(self, path: str, status: BackupStatus) -> None:
        """Update the stored status for *path* and emit :attr:`file_status_changed`.

        Args:
            path: Absolute path of the affected file.
            status: The new :class:`~domain.enums.backup_status.BackupStatus`.
        """
        self._statuses[path] = status
        self.file_status_changed.emit(path, status)

    def _check_session_complete(self) -> None:
        """Emit :attr:`backup_complete` if every file has reached a terminal state.

        Terminal states are ``DONE`` and ``FAILED``.  ``QUEUED`` and ``ACTIVE``
        files keep the session open.
        """
        terminal = {BackupStatus.DONE, BackupStatus.FAILED}
        if all(s in terminal for s in self._statuses.values()):
            self._is_active = False
            self._is_paused = False
            self.backup_complete.emit()

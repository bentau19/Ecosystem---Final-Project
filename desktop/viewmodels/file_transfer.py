"""
ViewModel for file transfer operations.

Gates all public transfer calls behind device connectivity and forwards
:class:`~services.file_transfer.FileTransferService` signals to the view
layer both verbatim (for specific handling) and as a unified
:class:`~domain.dto.file_transfer.FileTransferStatusDTO` (for status panels).
"""
from PySide6.QtCore import QObject, Signal, Slot

from domain.dto.file_transfer import (
    FileTransferStatusDTO,
    TransferDirection,
    TransferStatus,
)
from services.connectivity import ConnectivityService
from services.file_transfer import FileTransferService


class FileTransferViewModel(QObject):
    """ViewModel for file transfer operations.

    All send/receive activity is gated behind device connectivity — transfers
    dispatched before a phone connects are silently dropped.  Once
    :class:`~services.connectivity.ConnectivityService` emits
    ``device_connected``, the ViewModel becomes active and forwards every
    service signal until ``device_disconnected`` is received.

    In-flight transfers that complete (or fail) after a disconnect still
    surface their result so the view can inform the user.

    Signals:
        send_started (Signal[str]): Filename when a send begins.
        send_complete (Signal[str, int]): ``(filename, total_bytes)`` on success.
        send_error (Signal[str]): Exception message on send failure.
        receive_started (Signal[str]): Filename when a receive begins.
        receive_complete (Signal[str, str]): ``(filename, dest_path)`` on success.
        receive_error (Signal[str]): Exception message on receive failure.
        device_ready_changed (Signal[bool]): ``True`` when a device connects,
            ``False`` when it disconnects — use this to enable/disable UI controls.
        transfer_status_changed (Signal[object]): :class:`~domain.dto.file_transfer.FileTransferStatusDTO`
            emitted on every transfer event; convenient single-slot hook for
            status panels or notification widgets.
    """

    send_started: Signal = Signal(str)
    send_complete: Signal = Signal(str, int)
    send_error: Signal = Signal(str)

    receive_started: Signal = Signal(str)
    receive_complete: Signal = Signal(str, str)
    receive_error: Signal = Signal(str)

    device_ready_changed: Signal = Signal(bool)
    transfer_status_changed: Signal = Signal(object)  # FileTransferStatusDTO

    def __init__(
        self,
        file_transfer_service: FileTransferService,
        connectivity_service: ConnectivityService,
        parent: QObject | None = None,
    ) -> None:
        """Wire service and connectivity signals.

        Service signals are connected unconditionally — the connectivity guard
        lives in :meth:`send_file` / :meth:`receive_file` so that results from
        in-flight transfers always surface even after a disconnect.

        Args:
            file_transfer_service: The service that performs the actual I/O.
            connectivity_service: The service that manages device lifecycle signals.
            parent: Optional Qt parent for memory management.
        """
        super().__init__(parent)
        self._service: FileTransferService = file_transfer_service
        self._is_device_connected: bool = False

        # ── Service signal forwarding (always connected, never re-wired) ──────
        self._service.file_send_started.connect(self._on_send_started)
        self._service.file_send_complete.connect(self._on_send_complete)
        self._service.file_send_error.connect(self._on_send_error)
        self._service.file_receive_started.connect(self._on_receive_started)
        self._service.file_receive_complete.connect(self._on_receive_complete)
        self._service.file_receive_error.connect(self._on_receive_error)

        # ── Connectivity — drives the active/inactive state ───────────────────
        connectivity_service.device_connected.connect(self._on_device_connected)
        connectivity_service.device_disconnected.connect(self._on_device_disconnected)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_device_connected(self) -> bool:
        """Whether a device is currently connected."""
        return self._is_device_connected

    def send_file(self, path: str) -> None:
        """Send a local file to the connected device.

        No-ops silently when no device is connected so callers do not need
        to guard against it themselves.

        Args:
            path: Absolute path to the file to send.
        """
        if not self._is_device_connected:
            return
        self._service.send_file(path)

    def receive_file(self, dest_dir: str) -> None:
        """Wait for an incoming file and save it under *dest_dir*.

        No-ops silently when no device is connected.

        Args:
            dest_dir: Directory where the received file will be saved.
        """
        if not self._is_device_connected:
            return
        self._service.receive_file(dest_dir)

    # ── Connectivity slots ────────────────────────────────────────────────────

    @Slot()
    def _on_device_connected(self) -> None:
        """Activate the ViewModel when a device connects.

        Emits:
            device_ready_changed: With ``True``.
        """
        self._is_device_connected = True
        self.device_ready_changed.emit(True)

    @Slot()
    def _on_device_disconnected(self) -> None:
        """Deactivate the ViewModel when the device disconnects.

        Emits:
            device_ready_changed: With ``False``.
        """
        self._is_device_connected = False
        self.device_ready_changed.emit(False)

    # ── Service forwarding slots ──────────────────────────────────────────────

    @Slot(str)
    def _on_send_started(self, filename: str) -> None:
        self.send_started.emit(filename)
        self.transfer_status_changed.emit(
            FileTransferStatusDTO(filename, TransferDirection.SEND, TransferStatus.STARTED, "")
        )

    @Slot(str, int)
    def _on_send_complete(self, filename: str, total_bytes: int) -> None:
        self.send_complete.emit(filename, total_bytes)
        self.transfer_status_changed.emit(
            FileTransferStatusDTO(
                filename, TransferDirection.SEND, TransferStatus.COMPLETE, str(total_bytes)
            )
        )

    @Slot(str)
    def _on_send_error(self, error: str) -> None:
        self.send_error.emit(error)
        self.transfer_status_changed.emit(
            FileTransferStatusDTO("", TransferDirection.SEND, TransferStatus.ERROR, error)
        )

    @Slot(str)
    def _on_receive_started(self, filename: str) -> None:
        self.receive_started.emit(filename)
        self.transfer_status_changed.emit(
            FileTransferStatusDTO(filename, TransferDirection.RECEIVE, TransferStatus.STARTED, "")
        )

    @Slot(str, str)
    def _on_receive_complete(self, filename: str, dest_path: str) -> None:
        self.receive_complete.emit(filename, dest_path)
        self.transfer_status_changed.emit(
            FileTransferStatusDTO(
                filename, TransferDirection.RECEIVE, TransferStatus.COMPLETE, dest_path
            )
        )

    @Slot(str)
    def _on_receive_error(self, error: str) -> None:
        self.receive_error.emit(error)
        self.transfer_status_changed.emit(
            FileTransferStatusDTO("", TransferDirection.RECEIVE, TransferStatus.ERROR, error)
        )

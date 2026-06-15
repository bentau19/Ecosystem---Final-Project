from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from domain.dto.file_metadata import FileMetadataDTO
from domain.dto.file_receive_complete import FileReceiveCompleteDTO
from domain.dto.file_receive_prompt import FileReceivePromptDTO
from domain.dto.file_send_complete import FileSendCompleteDTO

if TYPE_CHECKING:
    from services.connectivity import ConnectivityService
    from services.file_transfer import FileTransferService


class FileTransferViewModel(QObject):
    """ViewModel for file transfer operations.

    All send and receive-metadata calls are gated behind device connectivity
    — operations dispatched before a device connects are silently dropped.
    In-flight transfers that complete or fail after a disconnect still surface
    their result so the view can inform the user.

    The receive flow is split into three explicit steps, each driven by the view:
        1. :meth:`receive_metadata` — start listening; fires :attr:`metadata_received`.
        2. :meth:`receive_file`     — user accepted; streams bytes to the chosen path.
        3. :meth:`reject_receive`   — user declined; sends the reject token.

    Steps 2 and 3 are **not** gated by connectivity so that in-flight operations
    that begin while connected can still resolve (or error gracefully) after a
    disconnect.

    Signals:
        send_complete (Signal[FileSendCompleteDTO]): Emitted on success.
        send_error (Signal[str]): Error message on send failure or rejection.
        metadata_received (Signal[FileReceivePromptDTO]): Emitted when incoming
            file metadata arrives — show an accept/reject prompt and call
            :meth:`receive_file` or :meth:`reject_receive` in response.
            The ``modified_at`` timestamp is stored internally and forwarded to
            the service automatically; the view does not need to handle it.
        receive_complete (Signal[FileReceiveCompleteDTO]): Emitted on success.
        receive_error (Signal[str]): Error message on receive failure.
        device_ready_changed (Signal[bool]): ``True`` when a device connects,
            ``False`` when it disconnects — use this to enable/disable UI controls.
    """

    send_complete: Signal = Signal(object)       # FileSendCompleteDTO
    send_error: Signal = Signal(str)

    metadata_received: Signal = Signal(object)   # FileReceivePromptDTO
    receive_complete: Signal = Signal(object)    # FileReceiveCompleteDTO
    receive_error: Signal = Signal(str)

    device_ready_changed: Signal = Signal(bool)

    def __init__(
            self,
            file_transfer_service: FileTransferService,
            connectivity_service: ConnectivityService,
            parent: QObject | None = None,
    ) -> None:
        """Wire service and connectivity signals.

        Service signals are connected unconditionally so that results from
        in-flight transfers surface even after a disconnect.  The connectivity
        guard lives in the public methods that initiate new operations.

        Args:
            file_transfer_service: The service that performs the actual I/O.
            connectivity_service: The service that manages device lifecycle signals.
            parent: Optional Qt parent for memory management.
        """
        super().__init__(parent)
        self._service: FileTransferService = file_transfer_service
        self._is_device_connected: bool = False
        # Holds the modified_at timestamp (Unix ms) received with the last
        # incoming metadata payload.  Forwarded to receive_file so the view
        # never needs to know about filesystem timestamps.
        self._pending_modified_at: int = 0

        # ── Service signal forwarding ─────────────────────────────────────────
        self._service.file_send_complete.connect(self._on_send_complete)
        self._service.file_send_rejected.connect(self._on_send_rejected)
        self._service.file_send_error.connect(self._on_send_error)
        self._service.file_metadata_received.connect(self._on_metadata_received)
        self._service.file_receive_complete.connect(self._on_receive_complete)
        self._service.file_receive_error.connect(self._on_receive_error)

        self._connectivity_service = connectivity_service
        # ── Connectivity ──────────────────────────────────────────────────────
        self._connectivity_service.device_connected.connect(self._on_device_connected)
        self._connectivity_service.device_disconnected.connect(self._on_device_disconnected)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def device_connected(self) -> bool:
        """Whether a device is currently connected."""
        return self._is_device_connected

    def send_file(self, path: str) -> None:
        """Send a local file to the connected device.

        No-ops silently when no device is connected.

        Args:
            path: Absolute path to the file to send.
        """
        if not self.device_connected:
            return
        self._service.send_file(path)

    def receive_metadata(self) -> None:
        """Start listening for an incoming file's metadata.

        No-ops silently when no device is connected.

        Emits:
            metadata_received: Forwarded from the service once metadata arrives.
        """
        if not self.device_connected:
            return
        self._service.receive_metadata()

    def receive_file(self, dest_path: str, file_size: int) -> None:
        """Accept the incoming transfer and save it to *dest_path*.

        Emits :attr:`receive_error` immediately when no device is connected so
        the view always receives feedback — even in the rare race where the
        device disconnects between the metadata prompt appearing and the user
        accepting it.

        The ``modified_at`` timestamp stored from the preceding
        :attr:`metadata_received` signal is forwarded to the service
        automatically so the received file's ``mtime`` matches the phone's
        original timestamp.

        Args:
            dest_path: Absolute path where the received file will be written.
            file_size: Exact byte count from the accepted metadata.
        """
        if not self.device_connected:
            self.receive_error.emit("Device disconnected — file transfer cancelled.")
            return
        self._service.receive_file(dest_path, file_size, self._pending_modified_at)

    def reject_receive(self) -> None:
        """Decline the incoming transfer.

        Not gated by connectivity — the service handles a stale transport
        gracefully by emitting :attr:`receive_error`.
        """
        self._service.reject_receive()

    # ── Connectivity slots ────────────────────────────────────────────────────

    @Slot()
    def _on_device_connected(self) -> None:
        # Gate new operations, start the file-transfer service, and notify the view.
        self._is_device_connected = True
        self._service.start()
        self.device_ready_changed.emit(True)

    @Slot()
    def _on_device_disconnected(self) -> None:
        # Drop the connectivity gate, stop the service, and notify the view.
        self._is_device_connected = False
        self._service.stop()
        self.device_ready_changed.emit(False)

    # ── Service forwarding slots ──────────────────────────────────────────────

    @Slot(object)
    def _on_send_complete(self, dto: FileSendCompleteDTO) -> None:
        # Forward send-complete DTO from service to the view layer.
        self.send_complete.emit(dto)

    @Slot(str)
    def _on_send_rejected(self, filename: str) -> None:
        # Translate a rejection into a user-readable error string.
        self.send_error.emit(f'"{filename}" was rejected by the receiver')

    @Slot(str)
    def _on_send_error(self, error: str) -> None:
        # Forward send errors unchanged.
        self.send_error.emit(error)

    @Slot(object)
    def _on_metadata_received(self, dto: FileMetadataDTO) -> None:
        # Store the timestamp for use in receive_file; forward only name+size to the view.
        self._pending_modified_at = dto.modified_at
        self.metadata_received.emit(FileReceivePromptDTO(filename=dto.name, size=dto.size))

    @Slot(object)
    def _on_receive_complete(self, dto: FileReceiveCompleteDTO) -> None:
        # Forward receive-complete DTO from service to the view layer.
        self.receive_complete.emit(dto)

    @Slot(str)
    def _on_receive_error(self, error: str) -> None:
        # Forward receive errors unchanged.
        self.receive_error.emit(error)

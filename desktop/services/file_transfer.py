"""
File transfer service.

Manages file sending and receiving over TauSync named channels on background
threads, emitting Qt signals on start, completion, or error.

Protocol — two sequential channels per transfer:
    1. ``file_meta`` — JSON ``{"name": <str>, "size": <int>}``.
    2. ``file_data``  — raw file bytes, exactly ``size`` bytes long.

Both peers must use the same channel names in the same order so TauSync's
symmetric-connect handshake can pair them.
"""
import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from domain.enums.file_transfer_channels import FileTransferChannels
from pipe import Server
from services.connectivity import ConnectivityService
from utils.decorators import threaded


class FileTransferService(QObject):
    """Sends and receives files over TauSync channels on background threads.

    Holds a reference to :class:`~services.connectivity.ConnectivityService`
    and reads ``connectivity.tau`` at the start of each call so reconnects that
    replace the underlying transport are handled transparently.

    All I/O runs on daemon threads via ``@threaded``; Qt's queued-connection
    mechanism keeps signal emissions safe on the main-thread slot side.

    Signals:
        file_send_started (Signal[str]): Filename once metadata is transmitted.
        file_send_complete (Signal[str, int]): ``(filename, total_bytes)`` on success.
        file_send_error (Signal[str]): Exception message on any send failure.
        file_receive_started (Signal[str]): Filename once metadata arrives.
        file_receive_complete (Signal[str, str]): ``(filename, dest_path)`` on success.
        file_receive_error (Signal[str]): Exception message on any receive failure.
    """

    file_send_started: Signal = Signal(str)
    file_send_complete: Signal = Signal(str, int)
    file_send_error: Signal = Signal(str)
    file_receive_started: Signal = Signal(str)
    file_receive_complete: Signal = Signal(str, str)
    file_receive_error: Signal = Signal(str)

    def __init__(
            self,
            connectivity: ConnectivityService,
            parent: QObject | None = None,
    ) -> None:
        """Initialize the service with the shared connectivity service.

        Args:
            connectivity: Application-level connectivity service; ``connectivity.tau``
                is accessed per-call so reconnects are handled transparently.
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._connectivity: ConnectivityService = connectivity
        self._threads: list = []
        self._listen_for_file_to_send()

    # ── Public API ─────────────────────────────────────────────────────────────

    def send_file(self, path: str) -> None:
        """Send a local file to the connected peer on a background thread.

        Args:
            path: Path to the file to send.  A missing file emits ``file_send_error``.

        Emits:
            file_send_started: With the filename once metadata is transmitted.
            file_send_complete: With ``(filename, total_bytes)`` on success.
            file_send_error: With the exception message on any failure.
        """
        self._send_file(path)

    def receive_file(self, dest_dir: str) -> None:
        """Receive an incoming file from the peer and save it under *dest_dir*.

        The destination directory is created automatically if it does not exist.

        Args:
            dest_dir: Directory path where the incoming file will be saved.

        Emits:
            file_receive_started: With the filename once metadata arrives.
            file_receive_complete: With ``(filename, dest_path)`` on success.
            file_receive_error: With the exception message on any failure.
        """
        self._receive_file(dest_dir)

    # ── Private threaded workers ───────────────────────────────────────────────

    @threaded
    def _send_file(self, path: str) -> None:
        """Background worker: transmit metadata then raw bytes to the peer.

        Args:
            path: Path to the local file to send.

        Emits:
            file_send_started: With the filename after metadata is written.
            file_send_complete: With ``(filename, total_bytes)`` on success.
            file_send_error: With the exception message on failure.
        """
        try:
            file_path: Path = Path(path)
            if not file_path.is_file():
                raise FileNotFoundError(f"File not found: {path}")

            filename: str = file_path.name
            file_size: int = file_path.stat().st_size
            tau = self._connectivity.tau

            # 1. Send metadata so the peer knows the filename and expected size.
            meta_payload: str = json.dumps({"name": filename, "size": file_size})
            with tau.connect(FileTransferChannels.REGULAR_FILE_METADATA) as meta_stream:
                meta_stream.write_string(meta_payload)
                meta_stream.flush()

            self.file_send_started.emit(filename)

            # 2. Stream raw bytes — write_file handles chunking internally.
            with tau.connect(FileTransferChannels.REGULAR_FILE_DATA) as data_stream:
                total_bytes: int = data_stream.write_file(str(file_path))

            self.file_send_complete.emit(filename, total_bytes)

        except Exception as exc:
            self.file_send_error.emit(str(exc))

    @threaded
    def _listen_for_file_to_send(self) -> None:
        """Background worker: listen on the named pipe for file paths to send.

        Blocks indefinitely, processing one file path per client connection.
        """
        pipe_name: str = r'\\.\pipe\FileSend'
        with Server(65536, 65536, pipe_name) as server:
            while True:
                server.wait_for_client()
                file_path = server.read()
                server.disconnect()
                print("heye")
                self.send_file(file_path)

    @threaded
    def _receive_file(self, dest_dir: str) -> None:
        """Background worker: read metadata then stream incoming bytes to disk.

        Args:
            dest_dir: Directory to write the received file into.

        Emits:
            file_receive_started: With the filename after metadata arrives.
            file_receive_complete: With ``(filename, dest_path)`` on success.
            file_receive_error: With the exception message on failure.
        """
        try:
            os.makedirs(dest_dir, exist_ok=True)
            tau = self._connectivity.tau

            # 1. Read metadata from the peer.
            with tau.connect(FileTransferChannels.REGULAR_FILE_METADATA) as meta_stream:
                raw_meta: bytes = meta_stream.read_all()
            meta: dict = json.loads(raw_meta.decode("utf-8"))
            filename: str = meta["name"]
            file_size: int = int(meta["size"])

            self.file_receive_started.emit(filename)

            # 2. Stream bytes straight to disk — no full-file buffering in RAM.
            dest_path: str = os.path.join(dest_dir, filename)
            with tau.connect(FileTransferChannels.REGULAR_FILE_DATA) as data_stream:
                data_stream.read_to_file(dest_path, file_size)

            self.file_receive_complete.emit(filename, dest_path)

        except Exception as exc:
            self.file_receive_error.emit(str(exc))

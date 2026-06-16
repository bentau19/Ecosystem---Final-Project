import datetime
import logging
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import sleep

from PySide6.QtCore import QObject, Signal

from domain.dto.file_metadata import FileMetadataDTO
from domain.dto.file_receive_complete import FileReceiveCompleteDTO
from domain.dto.file_send_complete import FileSendCompleteDTO
from domain.enums.file_transfer_channels import FileTransferChannels
from domain.enums.file_transfer_response import FileTransferResponse
from native import Server
from serializers.file_metadata import FileMetadataSerializer
from services.connectivity import ConnectivityService

logger = logging.getLogger(__name__)


# ── Data-channel timeout calibration ─────────────────────────────────────────
# Formula: timeout_s = ceil(_DATA_TIMEOUT_MULT * file_size_bytes) + _DATA_TIMEOUT_OFFSET_S
# Assumes a pessimistic 5 MB/s floor (slow mobile hotspot / congested Wi-Fi).
# Examples: 10 MB → 32 s  |  100 MB → 50 s  |  1 GB → 230 s (~4 min)
_DATA_TIMEOUT_MULT: float = 1 / 5_000_000   # 0.2 µs per byte ≈ 0.2 s per MB
_DATA_TIMEOUT_OFFSET_S: int = 30             # baseline before any bytes arrive


class FileTransferService(QObject):
    """Sends and receives files over TauSync channels on background threads.

    Reads ``connectivity.tau`` at the start of every call so reconnects that
    replace the underlying transport are handled transparently.

    All I/O is submitted to :attr:`_executor`; Qt's queued-connection
    mechanism keeps signal emissions safe on the main-thread side.

    Signals:
        file_send_complete (Signal[FileSendCompleteDTO]): Emitted on success.
        file_send_rejected (Signal[str]): Filename when the receiver declines.
        file_send_error (Signal[str]): Exception message on any send failure.
        file_metadata_received (Signal[FileMetadataDTO]): Emitted once the peer's
            metadata arrives — the view must show an accept/reject prompt and call
            :meth:`receive_file` or :meth:`reject_receive` in response.
            ``modified_at`` is Unix epoch milliseconds; ``0`` means the sender did
            not supply a timestamp.
        file_receive_complete (Signal[FileReceiveCompleteDTO]): Emitted on success.
        file_receive_error (Signal[str]): Exception message on any receive failure.
    """

    # ── Send-side signals ─────────────────────────────────────────────────────
    file_send_complete: Signal = Signal(object)  # FileSendCompleteDTO
    file_send_rejected: Signal = Signal(str)
    file_send_error: Signal = Signal(str)

    # ── Receive-side signals ──────────────────────────────────────────────────
    file_metadata_received: Signal = Signal(object)  # FileMetadataDTO
    file_receive_complete: Signal = Signal(object)  # FileReceiveCompleteDTO
    file_receive_error: Signal = Signal(str)

    def __init__(
            self,
            connectivity: ConnectivityService,
            parent: QObject | None = None,
    ) -> None:
        """Initialize with the shared connectivity service.

        Args:
            connectivity: Application-level connectivity service; ``connectivity.tau``
                is accessed per-call so reconnects are handled transparently.
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._connectivity: ConnectivityService = connectivity
        self._metadata_serializer: FileMetadataSerializer = FileMetadataSerializer()
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor()
        self._is_running: threading.Event = threading.Event()

        self._lifecycle_lock: threading.Lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        """Start the service on a background thread."""
        threading.Thread(target=self._start, daemon=True).start()

    def stop(self) -> None:
        """Stop the service on a background thread, joining all pending workers."""
        threading.Thread(target=self._stop, daemon=True).start()

    def _start(self) -> None:
        # Guard against double-start; launch the named-pipe listener on entry.
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._executor = ThreadPoolExecutor()
            self._is_running.set()
            self._executor.submit(self._listen_for_file_to_send)

    def _stop(self) -> None:
        # Clear the running flag then wait for all submitted work to finish.
        # The executor reference is captured inside the lock so a concurrent
        # _start() (which swaps self._executor) can never have its fresh pool
        # shut down by this stop.
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
            executor = self._executor
        executor.shutdown(wait=True, cancel_futures=True)

    def send_file(self, path: str) -> None:
        """Send a local file to the connected peer on a background thread.

        Args:
            path: Path to the file to send.  A missing file emits
                :attr:`file_send_error`.

        Emits:
            file_send_complete: With ``(filename, total_bytes)`` on success.
            file_send_rejected: With the filename when the receiver declines.
            file_send_error: With the exception message on any failure.
        """
        if not self._is_running.is_set():
            return

        self._executor.submit(self._send_file, path)

    def receive_metadata(self) -> None:
        """Listen for the peer's file-transfer metadata on a background thread.

        Opens the ``file_meta`` channel and reads the incoming JSON payload.
        Emits :attr:`file_metadata_received` once parsed so the view can show
        an accept/reject prompt.  The caller must then call either
        :meth:`receive_file` (accept) or :meth:`reject_receive` (decline).

        Emits:
            file_metadata_received: With ``(filename, size_bytes)`` on success.
            file_receive_error: With the exception message on failure.
        """
        if not self._is_running.is_set():
            return

        self._executor.submit(self._receive_metadata)

    def receive_file(self, dest_path: str, file_size: int, modified_at_ms: int = 0) -> None:
        """Accept the transfer and stream the incoming bytes to *dest_path*.

        Writes ``"accept"`` to the response channel so the sender opens the
        data channel, then streams exactly *file_size* bytes to *dest_path*.
        The parent directory is created automatically when it does not exist.
        When *modified_at_ms* is non-zero the file's ``mtime`` is set to the
        sender's original timestamp after writing.

        Must be called after :attr:`file_metadata_received` fires, in response
        to the user accepting the prompt.

        Args:
            dest_path: Absolute path where the received file will be written.
            file_size: Exact byte count to read, as reported in the metadata.
            modified_at_ms: Original last-modified time from the sender in Unix
                epoch milliseconds.  ``0`` (default) skips the ``os.utime`` call.

        Emits:
            file_receive_complete: With ``(filename, dest_path)`` on success.
            file_receive_error: With the exception message on failure.
        """
        if not self._is_running.is_set():
            return
        self._executor.submit(self._receive_file, dest_path, file_size, modified_at_ms)

    def reject_receive(self) -> None:
        """Decline the transfer by writing ``"reject"`` to the response channel.

        The sender reads this token and aborts without opening the data channel.
        Must be called after :attr:`file_metadata_received` fires, in response
        to the user declining the prompt.

        Emits:
            file_receive_error: With the exception message if the write fails.
        """

        if not self._is_running.is_set():
            return
        self._executor.submit(self._reject_receive)

    # ── Private Functions ─────────────────────────────────────────────────────────────

    def _data_timeout(self, file_size: int) -> int:
        """Compute a file-size-proportional connect timeout for the data channel.

        Formula: ``ceil(_DATA_TIMEOUT_MULT * file_size) + _DATA_TIMEOUT_OFFSET_S``

        Args:
            file_size: Transfer size in bytes.

        Returns:
            Timeout in whole seconds.
        """
        return math.ceil(_DATA_TIMEOUT_MULT * file_size) + _DATA_TIMEOUT_OFFSET_S

    def _send_file(self, path: str) -> None:
        # Steps: send metadata → wait for accept/reject → stream bytes.
        try:
            file_path: Path = Path(path)
            if not file_path.is_file():
                raise FileNotFoundError(f"File not found: {path}")
            filename: str = file_path.name
            file_size: int = file_path.stat().st_size
            tau = self._connectivity.tau

            # 1. Send metadata so the peer knows the filename and expected size.
            meta_payload: str = self._metadata_serializer.serialize(
                FileMetadataDTO(name=filename, size=file_size)
            )
            with tau.connect(FileTransferChannels.REGULAR_FILE_METADATA_PC_TO_ANDROID.value) as meta_stream:
                meta_stream.write_string(meta_payload)

            # 2. Wait for the receiver's accept/reject token.
            #    TauSync's 30-second handshake timeout is the upper bound.
            with tau.connect(FileTransferChannels.REGULAR_FILE_RESPONSE_FROM_ANDROID.value) as resp_stream:
                response: str = resp_stream.read_all().decode("utf-8").strip()

            if response == FileTransferResponse.REJECTED_FROM_ANDROID.value:
                self.file_send_rejected.emit(filename)
                return

            # 3. Stream raw bytes — write_file handles chunking internally.
            with tau.connect(
                FileTransferChannels.REGULAR_FILE_DATA_PC_TO_ANDROID.value,
                timeout_seconds=self._data_timeout(file_size),
            ) as data_stream:
                total_bytes: int = data_stream.write_file(str(file_path))

            self.file_send_complete.emit(FileSendCompleteDTO(filename=filename, total_bytes=total_bytes))

        except Exception as exc:
            self.file_send_error.emit(str(exc))

    def _receive_metadata(self) -> None:
        # Open the metadata channel, parse the JSON payload, and emit the result.
        try:
            tau = self._connectivity.tau
            with tau.connect(FileTransferChannels.REGULAR_FILE_METADATA_ANDROID_TO_PC.value) as meta_stream:
                raw: str = meta_stream.read_all().decode("utf-8")
            metadata: FileMetadataDTO = self._metadata_serializer.deserialize(raw)
            self.file_metadata_received.emit(metadata)
        except Exception as exc:
            self.file_receive_error.emit(str(exc))

    def _receive_file(self, dest_path: str, file_size: int, modified_at_ms: int) -> None:
        # Steps: send accept token → stream bytes straight to disk → restore mtime.
        try:
            os.makedirs(Path(dest_path).parent, exist_ok=True)
            tau = self._connectivity.tau

            # 1. Tell the sender we accept; it will open the data channel.
            with tau.connect(FileTransferChannels.REGULAR_FILE_RESPONSE_FROM_PC.value) as resp_stream:
                resp_stream.write_string(FileTransferResponse.ACCEPTED_FROM_PC.value)
                resp_stream.flush()

            # 2. Stream bytes straight to disk — no full-file buffering in RAM.
            with tau.connect(
                FileTransferChannels.REGULAR_FILE_DATA_ANDROID_TO_PC.value,
                timeout_seconds=self._data_timeout(file_size),
            ) as data_stream:
                data_stream.read_to_file(dest_path, file_size)

            # 3. Restore the sender's original mtime so the file sorts correctly
            #    in Explorer and apps that rely on filesystem timestamps.
            #    Skip when modified_at_ms is 0 (legacy sender or field absent).
            if modified_at_ms > 0:
                ts: float = modified_at_ms / 1000.0
                os.utime(dest_path, times=(ts, ts))

            self.file_receive_complete.emit(
                FileReceiveCompleteDTO(filename=Path(dest_path).name, dest_path=dest_path)
            )

        except Exception as exc:
            self.file_receive_error.emit(str(exc))

    def _reject_receive(self) -> None:
        # Write the reject token; sender aborts without opening the data channel.
        try:
            tau = self._connectivity.tau
            with tau.connect(FileTransferChannels.REGULAR_FILE_RESPONSE_FROM_PC.value) as resp_stream:
                resp_stream.write_string(FileTransferResponse.REJECTED_FROM_PC.value)
                resp_stream.flush()
        except Exception as exc:
            self.file_receive_error.emit(str(exc))

    def _listen_for_file_to_send(self) -> None:
        # Poll the named pipe for incoming file paths from FileHandler.exe and forward them.
        pipe_name: str = r'\\.\pipe\FileSend'
        with Server(65536, 65536, pipe_name) as server:
            while self._is_running.is_set():
                try:
                    timeout = datetime.timedelta(seconds=3)
                    server.wait_for_client(timeout)
                    # read() now returns raw bytes; the path is UTF-8 text on the wire.
                    file_path: str = server.read(timeout).decode("utf-8")
                    self.send_file(file_path)
                except TimeoutError:
                    # No client connected within the poll window — wait and retry.
                    sleep(3)
                    continue
                except Exception as exc:
                    logger.error("Pipe listener error: %s", exc)

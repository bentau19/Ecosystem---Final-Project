"""
File transfer service.

Manages file sending and receiving over TauSync named channels on background
threads, emitting Qt signals on start, completion, or error.

Protocol — two sequential channels per transfer:
    1. ``file_meta`` — JSON ``{"name": <str>, "size": <int>}``.
    2. ``file_data``  — raw file bytes, exactly ``size`` bytes long.

Both peers must open channels with the **same meeting-word** in the same order.
The Android side calls the complementary operation (send ↔ receive) using the
identical channel names so the TauSync symmetric-connect handshake pairs them.
"""
import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from enums.FileTransferChannels import FileTransferChannels
from services.connectivity import ConnectivityService
from utils.decorators import threaded


# Meeting-words agreed between PC and Android.  Both sides must use the same
# strings so TauSync's symmetric-connect handshake pairs the channels.
class FileTransferService(QObject):
    """Sends and receives files over TauSync channels on background threads.

    Uses :class:`~services.connectivity.ConnectivityService` rather than a
    raw :class:`~tausync_py.TauSync` snapshot for a deliberate reason:
    :meth:`~services.connectivity.ConnectivityService.connect_to_device` replaces
    ``ConnectivityService._tau`` with a fresh :class:`~tausync_py.TauSync` instance
    on every reconnect.  Any service that cached the old ``tau`` reference at
    construction time would be left holding a disposed transport and would emit
    confusing "instance has been disposed" errors.  Accessing
    ``connectivity.tau`` at the start of each call always returns the current
    live transport.

    All channel I/O runs on daemon :class:`threading.Thread` objects via the
    ``@threaded`` decorator.  PySide6's queued-connection mechanism ensures
    ``Signal.emit()`` from those threads is safe on the main-thread slot side.

    Signals:
        file_send_started (Signal[str]): Emitted with the filename as soon as
            metadata has been written to the peer (data transfer is about to start).
        file_send_complete (Signal[str, int]): Emitted with ``(filename,
            total_bytes)`` when every byte of the file has been sent successfully.
        file_send_error (Signal[str]): Emitted with the exception message string
            if the send fails at any stage (missing file, transport error, etc.).
        file_receive_started (Signal[str]): Emitted with the filename as soon as
            metadata has arrived from the peer (data transfer is about to start).
        file_receive_complete (Signal[str, str]): Emitted with
            ``(filename, dest_path)`` when the file has been fully written to disk.
        file_receive_error (Signal[str]): Emitted with the exception message string
            if the reception fails at any stage (bad metadata, transport error, etc.).
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
            connectivity: The application's
                :class:`~services.connectivity.ConnectivityService` singleton.
                The current live transport is read via ``connectivity.tau`` at
                the beginning of each transfer, keeping this service valid across
                reconnects that replace the underlying transport.
            parent: Optional parent :class:`~PySide6.QtCore.QObject` for Qt
                memory management.
        """
        super().__init__(parent)
        self._connectivity: ConnectivityService = connectivity
        self._threads: list = []

    # ── Public API ─────────────────────────────────────────────────────────────

    def send_file(self, path: str) -> None:
        """Send a local file to the connected peer on a background thread.

        Spawns a daemon thread immediately and returns.  Progress is reported
        via signals rather than a return value.

        Args:
            path: Absolute or relative path to the file to send.  Must exist
                at call time; a missing file emits ``file_send_error``.

        Emits:
            file_send_started: With the filename once metadata is transmitted.
            file_send_complete: With ``(filename, total_bytes)`` on success.
            file_send_error: With the exception message on any failure.
        """
        self._send_file(path)

    def receive_file(self, dest_dir: str) -> None:
        """Receive an incoming file from the peer and save it under *dest_dir*.

        Spawns a daemon thread immediately and returns.  The destination
        directory is created automatically if it does not exist.

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

        Reads ``connectivity.tau`` at invocation time so the method always
        uses the current live transport even if a reconnect has occurred since
        the service was constructed.

        Step 1 — ``file_meta`` channel:
            Sends ``{"name": filename, "size": file_size}`` as UTF-8 JSON so
            the peer knows the filename and can pre-allocate the destination.

        Step 2 — ``file_data`` channel:
            Streams the file directly from disk in 64 KB chunks using
            :meth:`~tausync_py.TauSyncStream.write_file`, keeping memory
            usage constant regardless of file size.

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

            # Fetch the live transport at call-time, not at construction-time.
            tau = self._connectivity.tau

            # 1. Transmit metadata so the peer knows filename + expected length.
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
    def _receive_file(self, dest_dir: str) -> None:
        """Background worker: read metadata then stream incoming bytes to disk.

        Reads ``connectivity.tau`` at invocation time so the method always
        uses the current live transport even if a reconnect has occurred since
        the service was constructed.

        Step 1 — ``file_meta`` channel:
            Reads the full JSON payload and parses ``name`` and ``size``.

        Step 2 — ``file_data`` channel:
            Reads exactly ``size`` bytes directly to disk using
            :meth:`~tausync_py.TauSyncStream.read_to_file`, keeping memory
            usage constant regardless of file size.

        Args:
            dest_dir: Directory to write the received file into.

        Emits:
            file_receive_started: With the filename after metadata arrives.
            file_receive_complete: With ``(filename, dest_path)`` on success.
            file_receive_error: With the exception message on failure.
        """
        try:
            os.makedirs(dest_dir, exist_ok=True)

            # Fetch the live transport at call-time, not at construction-time.
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

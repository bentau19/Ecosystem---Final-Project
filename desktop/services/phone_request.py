"""
Phone request service.

Dispatches incoming TauSync channel requests to registered operation
handlers on a background thread.
"""
import threading
from time import sleep
from typing import Callable

from services.connectivity import ConnectivityService
from domain.enums.file_transfer_channels import FileTransferChannels


class PhoneRequestService:
    """Dispatches incoming TauSync channel requests to registered handlers.

    Reads the peer's waiting channels on a background thread and invokes
    the matching operation handler for each one.  Callers register handlers
    via the public :attr:`operations` mapping before calling :meth:`start`.

    Attributes:
        operations: Map of channel name → handler callable, populated by
            callers before :meth:`start` is invoked.
    """

    def __init__(self, connectivity_service: ConnectivityService, file_transfer_service) -> None:
        """Initialize the service with the shared connectivity service.

        Args:
            connectivity_service: The application's shared
                :class:`~services.connectivity.ConnectivityService` instance.
                ``connectivity_service.tau`` is read at call-time so reconnects
                are handled transparently.
        """
        self._connectivity: ConnectivityService = connectivity_service
        self._threads: list[threading.Thread] = []
        self._is_running: threading.Event = threading.Event()
        self._lifecycle_lock: threading.Lock = threading.Lock()
        self._threads_lock: threading.Lock = threading.Lock()

        self.operations: dict[str, Callable[[], None]] = {
            FileTransferChannels.REGULAR_FILE_METADATA_ANDROID_TO_PC.value: file_transfer_service.receive_metadata,
        }
        self.start()

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the service on a background thread."""
        threading.Thread(target=self._start, daemon=True).start()

    def stop(self) -> None:
        """Stop the service on a background thread, joining all pending workers."""
        threading.Thread(target=self._stop, daemon=True).start()

    def _start(self) -> None:
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._is_running.set()
            self._spawn(self._listen_to_channels)

    def _stop(self) -> None:
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
            pending_threads: list[threading.Thread] = self._get_pending_threads()
            for t in pending_threads:
                if t == threading.current_thread():
                    continue
                t.join()

    # ── Private lifecycle ──────────────────────────────────────────────────────

    def _spawn(self, target, *args):
        """All thread creation must go through here."""
        if not self._is_running.is_set():
            return  # reject new spawns during teardown
        t = threading.Thread(target=target, args=args, daemon=True)
        with self._threads_lock:
            self._threads.append(t)
        t.start()

    def _get_pending_threads(self) -> list[threading.Thread]:
        threads: list[threading.Thread] = []
        while True:
            with self._threads_lock:
                pending_threads = [t for t in self._threads if t.is_alive()]
                if not pending_threads:
                    return threads
                threads.extend(pending_threads)

    def _listen_to_channels(self) -> None:
        """Read the peer's waiting channels and dispatch to registered handlers.

        Retrieves the list of channel names the peer is waiting on and calls
        the registered handler for each.  Channels with no registered handler
        are silently skipped.
        """
        while not self._connectivity.connected:
            sleep(5)
        tau = self._connectivity.tau
        channels = tau.get_peer_waiting_words()
        for channel in channels:
            handler = self.operations.get(channel)
            if handler is not None:
                handler()

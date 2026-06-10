import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from typing import Any

from services.connectivity import ConnectivityService
from services.file_transfer import FileTransferService
from domain.enums.file_transfer_channels import FileTransferChannels
from domain.enums.session_channels import SessionChannels


class PhoneRequestService:
    """Dispatches incoming TauSync channel requests to registered handlers.

    Reads the peer's waiting channels on a background thread and invokes
    the matching operation handler for each one.  Callers register handlers
    via the public :attr:`operations` mapping before calling :meth:`start`.

    Attributes:
        operations: Map of channel name → handler callable, populated by
            callers before :meth:`start` is invoked.
    """

    def __init__(
            self,
            connectivity_service: ConnectivityService,
            file_transfer_service: FileTransferService,
    ) -> None:
        """Initialize the service with the shared connectivity service.

        Args:
            connectivity_service: The application's shared
                :class:`~services.connectivity.ConnectivityService` instance.
                ``connectivity_service.tau`` is read at call-time so reconnects
                are handled transparently.
            file_transfer_service: The application's shared
                :class:`~services.file_transfer.FileTransferService` instance,
                whose :meth:`~services.file_transfer.FileTransferService.receive_metadata`
                is registered as the handler for incoming file-transfer requests.
        """
        self._connectivity: ConnectivityService = connectivity_service
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor()
        self._is_running: threading.Event = threading.Event()
        self._lifecycle_lock: threading.Lock = threading.Lock()

        self.operations: dict[str, Callable[[], None]] = {
            FileTransferChannels.REGULAR_FILE_METADATA_ANDROID_TO_PC.value: file_transfer_service.receive_metadata,
            SessionChannels.DISCONNECT_FROM_PHONE.value: self._connectivity.stop,
        }

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the service on a background thread."""
        threading.Thread(target=self._start, daemon=True).start()

    def stop(self) -> None:
        """Stop the service on a background thread, joining all pending workers."""
        threading.Thread(target=self._stop, daemon=True).start()

    def _start(self) -> None:
        # Guard against double-start; launch the channel-listener loop on entry.
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._executor = ThreadPoolExecutor()
            self._is_running.set()
            self._spawn(self._listen_to_channels)

    def _stop(self) -> None:
        # Clear the running flag then wait for all submitted work to finish.
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
        self._executor.shutdown(wait=True, cancel_futures=True)

    # ── Private lifecycle ──────────────────────────────────────────────────────

    def _spawn(self, target: Callable[..., None], *args: Any) -> None:
        # Reject new submissions during teardown.
        if not self._is_running.is_set():
            return
        self._executor.submit(target, *args)

    def _listen_to_channels(self) -> None:
        # Block until a device is connected, then dispatch each waiting channel to its handler.

        while self._is_running.is_set() and not self._connectivity.connected:
            sleep(5)

        while self._is_running.is_set():
            try:
                tau = self._connectivity.tau
                channels = tau.get_peer_waiting_words()
                for channel in channels:
                    handler = self.operations.get(channel)
                    if handler is not None:
                        handler()
            except Exception as exc:
                # get_peer_waiting_words() raises RuntimeError when the peer has
                # gone away (e.g. Android crash / force-stop).  Trigger the same
                # teardown path as a graceful phone-initiated disconnect so the UI
                # navigates back to the login screen automatically.
                print(
                    f"[PhoneRequestService] ⚠ Channel poll failed "
                    f"— peer may have disconnected: {exc}"
                )
                self._connectivity.stop()
                break
            sleep(5)

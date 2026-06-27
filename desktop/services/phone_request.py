import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from typing import Callable

from domain.enums.backup_channels import BackupChannels
from domain.enums.file_transfer_channels import FileTransferChannels
from domain.enums.session_channels import SessionChannels
from domain.enums.device_info_channels import DeviceInfoChannels
from services.backup import BackupService
from services.connectivity import ConnectivityService
from services.device_info import DeviceInfoService
from services.file_transfer import FileTransferService
from services.lifecycle import LifecycleFlag

logger = logging.getLogger(__name__)


class PhoneRequestService(LifecycleFlag):
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
            device_info_service: DeviceInfoService,
            backup_service: BackupService,
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
            backup_service: The application's shared
                :class:`~services.backup.BackupService` instance, whose
                :meth:`~services.backup.BackupService.receive_manifest` is
                registered as the handler for incoming backup manifest requests.
        """
        self._connectivity: ConnectivityService = connectivity_service
        self._device_info_service: DeviceInfoService = device_info_service
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor()
        self._is_running: threading.Event = threading.Event()
        self._init_lifecycle()
        self._lifecycle_lock: threading.Lock = threading.Lock()

        self.operations: dict[str, Callable[[], None]] = {
            FileTransferChannels.REGULAR_FILE_METADATA_ANDROID_TO_PC.value: file_transfer_service.receive_metadata,
            BackupChannels.BACKUP_MANIFEST_FROM_ANDROID.value: backup_service.receive_manifest,
            SessionChannels.DISCONNECT_FROM_PHONE.value: self._connectivity.stop,
            DeviceInfoChannels.PC_NAME.value: self._device_info_service.send_pc_name
        }

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the service on a background thread."""
        threading.Thread(target=self._start, daemon=True).start()

    def stop(self) -> None:
        """Stop the service on a daemon thread (fire-and-forget)."""
        threading.Thread(target=self._stop, daemon=True).start()

    def _start(self) -> None:
        # Guard against double-start; launch the channel-listener loop on entry.
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._executor = ThreadPoolExecutor()
            self._is_running.set()
            self._mark_started()
            self._executor.submit(self._listen_to_channels)

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
            self._mark_stopped()

    # ── Private lifecycle ──────────────────────────────────────────────────────

    def _listen_to_channels(self) -> None:
        # Block until a device is connected, then dispatch each waiting channel to its handler.
        while self._is_running.is_set() and not self._connectivity.connected:
            sleep(5)

        while self._is_running.is_set():
            tau = self._connectivity.tau
            try:
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
                #
                # Guard against stale pollers: only tear connectivity down when
                # the transport this loop was polling is still the current one
                # and this service is still running.  Otherwise a leftover poll
                # thread from the previous session could stop a freshly
                # restarted (re-listening) ConnectivityService.
                if self._is_running.is_set() and tau is self._connectivity.tau:
                    logger.warning("Channel poll failed — peer may have disconnected: %s", exc)
                    self._connectivity.stop()
                break
            sleep(5)

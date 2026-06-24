import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from PySide6.QtCore import QObject, Signal

import utils
from domain.entities.device_info import DeviceEntity
from domain.enums.device_info_channels import DeviceInfoChannels
from repositories.device import DeviceRepository
from services.connectivity import ConnectivityService
from services.lifecycle import LifecycleFlag
# Imported for its side effect of binding the `network` submodule onto the
# `utils` package object so `utils.network.*` below resolves correctly.
from utils import network

logger = logging.getLogger(__name__)


class DeviceInfoService(LifecycleFlag, QObject):
    """Reads device metadata from TauSync channels and emits a DeviceEntity.

    Depends on a live :class:`~tausync_py.TauSync` transport (obtained from
    :class:`~services.connectivity.ConnectivityService`) and the device
    repository (to guarantee UUID uniqueness when the remote device has no
    previously assigned ID).

    All channel reads run on a background :class:`threading.Thread` spawned
    submitted to :attr:`_executor` so the UI thread is never blocked.
    PySide6's queued connection mechanism ensures ``Signal.emit()`` is safe.

    Signals:
        device_info_ready (Signal[object]): Emitted with a fully-populated
            :class:`~entities.device_info.DeviceEntity` once all channel reads
            complete successfully.
        device_saved (Signal[object]): Emitted with the
            :class:`~domain.entities.device_info.DeviceEntity` after
            :meth:`save` writes it to the repository.
        read_error (Signal[str]): Emitted with the exception message string if
            any channel read raises an exception.
        device_fetched (Signal[object]): Emitted with the
            :class:`~domain.entities.device_info.DeviceEntity` matching a
            :meth:`fetch_device_by_id` lookup, or ``None`` if not found.
        all_devices_fetched (Signal[list]): Emitted with
            ``list[DeviceEntity]`` when :meth:`fetch_all_devices` completes.
    """

    device_info_ready: Signal = Signal(object)
    device_saved: Signal = Signal(object)
    read_error: Signal = Signal(str)
    device_fetched: Signal = Signal(object)  # DeviceEntity | None
    all_devices_fetched: Signal = Signal(list)  # list[DeviceEntity]
    _CHANNEL_TIMEOUT: int = 10  # seconds to wait for each device-info channel

    def __init__(
            self,
            connectivity: ConnectivityService,
            repository: DeviceRepository,
            parent: QObject | None = None,
    ) -> None:
        """Initialize the service with the shared connectivity service and repository.

        Args:
            connectivity: The application's
                :class:`~services.connectivity.ConnectivityService` singleton.
                ``listen()`` or ``connect_to()`` must have been called on it
                before :meth:`fetch_device_info` is invoked.
            repository: The shared :class:`~repositories.device.DeviceRepository`
                instance from the application's DI root, used to check for
                existing device IDs before generating new ones.
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._connectivity: ConnectivityService = connectivity
        self._device_repository: DeviceRepository = repository

        self._executor: ThreadPoolExecutor = ThreadPoolExecutor()
        self._lifecycle_lock: threading.Lock = threading.Lock()
        self._is_running: threading.Event = threading.Event()
        self._init_lifecycle()

    # ── Public API ─────────────────────────────────────────────────────────────

    def save(self, entity: DeviceEntity) -> None:
        """Persist *entity* to the repository and emit :attr:`device_saved`.

        Args:
            entity: The :class:`~domain.entities.device_info.DeviceEntity` to
                persist.  Delegates directly to the underlying repository.

        Emits:
            device_saved: With the saved entity after the repository write.
        """
        if not self._is_running.is_set():
            return
        self._executor.submit(self._save, entity)

    def fetch_device_by_id(self, device_id: str) -> None:
        """Fetch a stored device by ID on a background thread.

        Gated on :attr:`_is_running` for lifecycle consistency.  Call
        :meth:`start` before invoking this method — ``DeviceViewModel``
        does so during construction so DB reads at app startup are safe.

        Args:
            device_id: The UUID of the device to retrieve.

        Emits:
            device_fetched: With the matching
                :class:`~domain.entities.device_info.DeviceEntity`, or
                ``None`` if no such device exists in the repository.
        """
        if not self._is_running.is_set():
            return
        self._executor.submit(self._fetch_device_by_id, device_id)

    def fetch_all_devices(self) -> None:
        """Fetch all stored devices on a background thread.

        Gated on :attr:`_is_running` for lifecycle consistency.  Call
        :meth:`start` before invoking this method — ``DeviceViewModel``
        does so during construction so DB reads at app startup are safe.

        Emits:
            all_devices_fetched: With the full
                ``list[DeviceEntity]`` currently stored in the repository.
        """
        if not self._is_running.is_set():
            return
        self._executor.submit(self._fetch_all_devices)

    def start(self) -> None:
        """Start the service on a background thread."""
        threading.Thread(target=self._start, daemon=True).start()

    def stop(self) -> None:
        """Stop the service on a daemon thread (fire-and-forget)."""
        threading.Thread(target=self._stop, daemon=True).start()

    def restart(self) -> None:
        """Stop then start the service sequentially on one background thread.

        Unlike calling :meth:`stop` followed by :meth:`start` (two independent
        threads racing on the lifecycle lock — start could win first and
        no-op, leaving the service dead), this guarantees the stop fully
        completes before the start runs.  Used on device disconnect so the
        login screen's DB reads (:meth:`fetch_all_devices`,
        :meth:`fetch_device_by_id`) keep working for the next session.
        """

        def _restart() -> None:
            self._stop()
            self._start()

        threading.Thread(target=_restart, daemon=True).start()

    def fetch_device_info(self) -> None:
        """Request a fresh device-info read from TauSync channels on a background thread.

        Gated on :attr:`_is_running` — call :meth:`start` first.

        Emits:
            device_info_ready: With the populated
                :class:`~domain.entities.device_info.DeviceEntity` on success.
            read_error: With the exception message string on failure.
        """
        if not self._is_running.is_set():
            return
        self._executor.submit(self._get_device_info)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _start(self) -> None:
        # Guard against double-start with the lifecycle lock.
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._executor = ThreadPoolExecutor()
            self._is_running.set()
            self._mark_started()

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

    def _save(self, entity: DeviceEntity) -> None:
        # Persist entity via repository, then emit both the saved signal and
        # device_info_ready so the ViewModel only receives the entity after it
        # is guaranteed to be on disk.
        self._device_repository.save(entity)
        self.device_saved.emit(entity)
        self.device_info_ready.emit(entity)

    def _fetch_device_by_id(self, device_id: str) -> None:
        # Look up the entity and emit device_fetched (None if not found).
        entity = self._device_repository.get_by_id(device_id)
        self.device_fetched.emit(entity)

    def _fetch_all_devices(self) -> None:
        # Retrieve the full device list and emit it for the ViewModel to consume.
        devices = self._device_repository.get_all()
        self.all_devices_fetched.emit(devices)

    def _get_device_info(self) -> None:
        # Read all device channels in parallel, build the entity, persist, and emit.
        tau = self._connectivity.tau
        if not tau.is_connected:
            return
        try:
            read = utils.network.read_string_from_channel
            t = self._CHANNEL_TIMEOUT
            with ThreadPoolExecutor() as pool:
                f_id = pool.submit(read, tau, DeviceInfoChannels.ID.value, t)
                f_name = pool.submit(read, tau, DeviceInfoChannels.NAME_FROM_ANDROID.value, t)
                f_os = pool.submit(read, tau, DeviceInfoChannels.OS_FROM_ANDROID.value, t)
                f_battery = pool.submit(read, tau, DeviceInfoChannels.BATTERY_LEVEL_FROM_ANDROID.value, t)
                f_charging = pool.submit(read, tau, DeviceInfoChannels.BATTERY_CHARGING_FROM_ANDROID.value, t)
                f_stor_tot = pool.submit(read, tau, DeviceInfoChannels.STORAGE_TOTAL_FROM_ANDROID.value, t)
                f_stor_use = pool.submit(read, tau, DeviceInfoChannels.STORAGE_USED_FROM_ANDROID.value, t)
                f_ip = pool.submit(read, tau, DeviceInfoChannels.IP_FROM_ANDROID.value, t)
            entity = DeviceEntity(
                id=f_id.result(),
                tag="",
                name=f_name.result(),
                os=f_os.result(),
                battery_level=int(f_battery.result()),
                battery_charging=f_charging.result().lower() == "true",
                storage_total=round(int(f_stor_tot.result()) / (1000 ** 3), 1),
                storage_used=round(int(f_stor_use.result()) / (1000 ** 3), 1),
                last_connected=date.today(),
                ip=f_ip.result(),
            )
            self._save(entity)

        except Exception as exc:
            self.read_error.emit(str(exc))

    def send_pc_name(self) -> None:
        self._executor.submit(self._send_pc_name)


    def _send_pc_name(self):
        # Send PC name to the connected Android device.
        # Runs on a background thread so it doesn't block the main device info read.
        tau = self._connectivity.tau
        if not tau.is_connected:
            return
        try:
            pc_name = utils.network.get_pc_name()
            utils.network.write_string_to_channel(tau, DeviceInfoChannels.PC_NAME.value, pc_name, self._CHANNEL_TIMEOUT)
        except Exception as e:
            logger.warning("Failed to send PC name to Android: %s", e)

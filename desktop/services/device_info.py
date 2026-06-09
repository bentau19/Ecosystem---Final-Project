"""
Device-info service.

Reads device metadata from TauSync named channels on a background thread
and emits a fully-populated DeviceEntity so the ViewModel can persist and
display it without touching the network layer directly.
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from PySide6.QtCore import QObject, Signal

import utils
from domain.entities.device_info import DeviceEntity
from domain.enums.device_info_channels import DeviceInfoChannels
from repositories.device import DeviceRepository
from services.connectivity import ConnectivityService
from utils import network


class DeviceInfoService(QObject):
    """Reads device metadata from TauSync channels and emits a DeviceEntity.

    Depends on a live :class:`~tausync_py.TauSync` transport (obtained from
    :class:`~services.connectivity.ConnectivityService`) and the device
    repository (to guarantee UUID uniqueness when the remote device has no
    previously assigned ID).

    All channel reads run on a background :class:`threading.Thread` via the
    ``@threaded`` decorator so the UI thread is never blocked. PySide6's queued
    connection mechanism ensures ``Signal.emit()`` from that thread is safe.

    Signals:
        device_info_ready (Signal[object]): Emitted with a fully-populated
            :class:`~entities.device_info.DeviceEntity` once all channel reads
            complete successfully.
        read_error (Signal[str]): Emitted with the exception message string if
            any channel read raises an exception.
    """

    device_info_ready = Signal(object)
    device_saved = Signal(object)
    read_error = Signal(str)
    device_fetched = Signal(object)  # DeviceEntity | None
    all_devices_fetched = Signal(list)  # list[DeviceEntity]

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

        self._threads: list[threading.Thread] = []

        self._lifecycle_lock: threading.Lock = threading.Lock()
        self._is_running: threading.Event = threading.Event()
        self._threads_lock: threading.Lock = threading.Lock()

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
        self._spawn(self._save, entity)

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
        self._spawn(self._fetch_device_by_id, device_id)

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
        self._spawn(self._fetch_all_devices)

    def start(self) -> None:
        """Start the service on a background thread."""
        threading.Thread(target=self._start, daemon=True).start()

    def stop(self) -> None:
        """Stop the service on a background thread, joining all pending workers."""
        threading.Thread(target=self._stop, daemon=True).start()

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
        self._spawn(self._get_device_info)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _spawn(self, target, *args) -> None:
        # Reject new spawns during teardown to avoid work after _is_running is cleared.
        if not self._is_running.is_set():
            return
        t = threading.Thread(target=target, args=args, daemon=True)
        with self._threads_lock:
            self._threads.append(t)
        t.start()

    def _start(self) -> None:
        # Guard against double-start with the lifecycle lock.
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._is_running.set()

    def _stop(self) -> None:
        # Join every worker except the calling thread to avoid a deadlock.
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
            pending_threads: list[threading.Thread] = self._get_pending_threads()
            for t in pending_threads:
                if t == threading.current_thread():
                    continue
                t.join()

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

    def _get_pending_threads(self) -> list[threading.Thread]:
        # Snapshot alive threads under the lock so callers can join without holding it.
        with self._threads_lock:
            return [t for t in self._threads if t.is_alive()]

    _CHANNEL_TIMEOUT: int = 30  # seconds to wait for each device-info channel

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

            # Send PC name to the connected Android device on a background thread.
            self._spawn(self._send_pc_name)
            # device_info_ready is emitted from _save (after the DB write) — not here.
        except Exception as exc:
            self.read_error.emit(str(exc))

    def _send_pc_name(self) -> None:
        # Send PC name to the connected Android device.
        # Runs on a background thread so it doesn't block the main device info read.
        tau = self._connectivity.tau
        if not tau.is_connected:
            return
        try:
            pc_name = utils.network.get_pc_name()
            utils.network.write_string_to_channel(tau, DeviceInfoChannels.PC_NAME.value, pc_name)
        except Exception as e:
            print(f"[Desktop] Warning: Failed to send PC name to Android: {e}")

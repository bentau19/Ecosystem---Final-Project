from PySide6.QtCore import QObject, Signal, Slot, QTimer

from domain.dto.device_info import (
    DeviceInfoDTO,
    DeviceNameDTO,
    DeviceOSDTO,
    DeviceBatteryDTO,
    DeviceStorageDTO,
)
from domain.entities.device_info import DeviceEntity
from resources.paths import Icons
from services.connectivity import ConnectivityService
from services.device_info import DeviceInfoService


class DeviceViewModel(QObject):
    """ViewModel for the currently connected device's info dashboard.

    Reads a single ``DeviceEntity`` from the repository and exposes its fields
    to the view as a list of typed ``DeviceInfoDTO`` subclasses — one per
    dashboard card (name, OS, battery, storage).

    A periodic :class:`~PySide6.QtCore.QTimer` fires every 10 minutes to pull
    refreshed data from the device-info service while a device is connected.

    Connection is phone-initiated only — the phone scans a QR code or
    discovers the PC over Bluetooth. The PC never dials out, so there is no
    ``connect_to_device`` path in this ViewModel.

    Signals:
        device_infos_updated (Signal[object]): Emitted with
            ``list[DeviceInfoDTO]`` whenever the current device's data changes.
        device_connecting (Signal): Emitted at the very start of any connection
            attempt (QR or Bluetooth path) so the UI can show a loading state
            before the TCP handshake or channel reads complete.
        device_connected (Signal): Emitted when the connectivity service
            reports a successful device connection.
        device_disconnecting (Signal): Emitted immediately when
            ``disconnect_device`` is called, before the background tear-down
            begins, so the UI can show a "Disconnecting…" state.
        device_disconnected (Signal): Forwarded from the connectivity service
            after the device is disconnected.
    """

    device_infos_updated: Signal = Signal(object)

    device_connecting: Signal = Signal()
    """Emitted at the start of any connection attempt (QR or Bluetooth path)."""
    device_connected: Signal = Signal()
    device_disconnecting: Signal = Signal()
    """Emitted immediately when a PC-initiated disconnect begins."""
    device_disconnected: Signal = Signal()
    device_info_error: Signal = Signal(str)
    """Emitted when device-info channel reads fail — forwarded from DeviceInfoService.read_error."""
    connection_error: Signal = Signal(str)
    """Emitted when the TCP listener crashes — forwarded from ConnectivityService.connection_error."""
    mode_changed: Signal = Signal(bool)
    """Forwarded from ConnectivityService.mode_changed. True = Bluetooth, False = WiFi."""

    _ONE_MINUTES: int = 60 * 1000

    def __init__(
            self,
            connectivity_service: ConnectivityService,
            device_info_service: DeviceInfoService,
            parent: QObject | None = None,
    ) -> None:
        """Initialize the ViewModel and wire up service signals.

        Args:
            connectivity_service: The service that manages the TauSync
                connection and emits device lifecycle signals.
            device_info_service: The service that reads device metadata from
                TauSync channels, persists entities, and exposes repository
                read operations.
            parent: Optional Qt parent object for memory management.
        """
        super().__init__(parent)
        self._connectivity_service: ConnectivityService = connectivity_service
        self._device_info_service: DeviceInfoService = device_info_service

        self._connectivity_service.device_connected.connect(self._on_device_connected)
        self._connectivity_service.device_disconnecting.connect(self.device_disconnecting)
        self._connectivity_service.device_disconnected.connect(self._on_device_disconnected)
        self._connectivity_service.connection_error.connect(self.connection_error)
        self._connectivity_service.mode_changed.connect(self.mode_changed)
        self._device_info_service.device_info_ready.connect(self._on_device_info_ready)
        self._device_info_service.device_fetched.connect(self._on_device_fetched)
        self._device_info_service.read_error.connect(self.device_info_error)

        # Start connectivity immediately so it listens before any device connects.
        # DeviceInfoService also starts at launch — fetch_device_by_id is needed
        # by the dashboard before a new connection exists.  The network path
        # (fetch_device_info) is self-guarded by tau.is_connected and is safe to
        # call on a live service.
        # All other services (FileTransferService, PhoneRequestService) start only
        # in _on_device_connected and stop in _on_device_disconnected.

        self._connectivity_service.start()
        self._device_info_service.start()

        self._refresh_timer: QTimer = QTimer(self)
        self._refresh_timer.timeout.connect(self._request_device_info_refresh)
        self._refresh_timer.start(self._ONE_MINUTES)

        self._current_device_connected_id: str = ""

        # Set during app exit so _on_device_disconnected does not re-arm the
        # connectivity listener while every service is being torn down.
        self._is_shutting_down: bool = False

    # ── Public API ────────────────────────────────────────────────────────────

    def load_current_device_info(self) -> None:
        """Request the current device from the service on a background thread.

        The result arrives asynchronously via :attr:`device_infos_updated`
        once :meth:`~services.device_info.DeviceInfoService.fetch_device_by_id`
        completes and :meth:`_on_device_fetched` handles the response.

        Emits:
            device_infos_updated: Asynchronously, with ``list[DeviceInfoDTO]``
                if the current device is found in the repository.
        """

        self._device_info_service.fetch_device_by_id(self._current_device_connected_id)

    def update_device_info(self) -> None:
        """Trigger a manual refresh of the current device's info.

        Delegates to the device-info service to re-read all device channels
        on a background thread.
        """
        self._request_device_info_refresh()

    @property
    def is_device_info_loaded(self) -> bool:
        """``True`` once device info has been fetched at least once this session."""
        return bool(self._current_device_connected_id)

    @property
    def is_bluetooth_mode(self) -> bool:
        """``True`` when the service is in Bluetooth mode, ``False`` for WiFi (QR)."""
        return self._connectivity_service.is_bluetooth_mode

    def toggle_connection_mode(self) -> None:
        """Switch between Bluetooth and WiFi connection modes."""
        self._connectivity_service.set_mode(not self._connectivity_service.is_bluetooth_mode)

    def disconnect_device(self) -> None:
        """Disconnect the currently connected device via the connectivity service.

        Delegates to :meth:`~services.connectivity.ConnectivityService.stop`
        which emits ``device_disconnecting`` before any teardown begins.  The
        forwarding wire in ``__init__`` propagates that signal to this
        ViewModel's own ``device_disconnecting`` — no direct emit here to avoid
        the signal firing twice on the PC-initiated path.
        """
        self._connectivity_service.stop()

    def prepare_shutdown(self) -> None:
        """Arm shutdown mode so the app can tear down without re-listening.

        Called from :meth:`~views.main_window.MainWindow._begin_shutdown` (on
        every exit path) before any service is stopped.  Stops the periodic
        refresh timer and sets the
        flag that makes :meth:`_on_device_disconnected` skip its normal
        connectivity restart — otherwise stopping the connectivity service
        would immediately spawn a fresh listener as the process is exiting.
        """
        self._is_shutting_down = True
        self._refresh_timer.stop()

    # ── Private helpers ────────────────────────────────────────────────────────

    def _request_device_info_refresh(self) -> None:
        # Delegate to the service so the timer and update_device_info() share one path.
        self._device_info_service.fetch_device_info()

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot(object)
    def _on_device_info_ready(self, entity: DeviceEntity) -> None:
        # Track the connected device ID so load_device_info() fetches the right entity.
        self._current_device_connected_id = entity.id
        self.device_infos_updated.emit(self._to_device_info_dtos(entity))

    @Slot(object)
    def _on_device_fetched(self, entity: DeviceEntity | None) -> None:
        # Silently drop None — no device in the repository yet.
        if entity is None:
            return
        self.device_infos_updated.emit(self._to_device_info_dtos(entity))

    @Slot(object)
    def _on_entity_saved(self, entity: DeviceEntity) -> None:
        # Refresh the dashboard cards whenever a save completes.
        self.device_infos_updated.emit(self._to_device_info_dtos(entity))

    @Slot()
    def _on_device_connected(self) -> None:
        # Emit device_connecting so the login-screen overlay starts.
        self.device_connecting.emit()
        # Start the info service so channel reads can proceed, then fetch immediately.
        self._device_info_service.start()
        self._device_info_service.fetch_device_info()
        self.device_connected.emit()

    @Slot()
    def _on_device_disconnected(self) -> None:
        # Only connectivity and device-info restart after a disconnect; every
        # other service (backup, phone-request, file-transfer) is stopped via
        # the device_disconnected wiring and starts again on the next connect.
        #
        # restart() runs stop-then-start sequentially on one thread, joining
        # any lingering network threads from the previous session before
        # re-enabling DB reads (fetch_all_devices / fetch_device_by_id are
        # needed by the login screen before the next connection exists).
        #
        # connectivity.start() is safe here: ConnectivityService emits
        # device_disconnected only after its own executor is fully drained,
        # so this restart can never race the previous shutdown.
        #
        # During app exit the restart is suppressed: prepare_shutdown() has set
        # _is_shutting_down, so stopping connectivity does not re-arm a listener
        # that would otherwise hang the process at interpreter shutdown.
        # self._device_info_service.stop()
        if not self._is_shutting_down:
            self._connectivity_service.start()
        # self._device_info_service.start()
        self.device_disconnected.emit()

    # ── Conversion ────────────────────────────────────────────────────────────

    @staticmethod
    def _to_device_info_dtos(entity: DeviceEntity) -> list[DeviceInfoDTO]:
        # Map entity fields to the typed DTO subclasses the view layer expects.
        return [
            DeviceNameDTO(
                title="Name",
                icon_path=Icons.SMARTPHONE,
                name=entity.name,
            ),
            DeviceOSDTO(
                title="OS",
                icon_path=Icons.ANDROID,
                os=entity.os,
            ),
            DeviceBatteryDTO(
                title="Battery",
                icon_path=Icons.BATTERY,
                level=entity.battery_level,
                is_charging=entity.battery_charging,
            ),
            DeviceStorageDTO(
                title="Storage",
                icon_path=Icons.STORAGE,
                used=entity.storage_used,
                total=entity.storage_total,
            ),
        ]


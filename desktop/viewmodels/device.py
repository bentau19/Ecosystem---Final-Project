import random
import uuid

from PySide6.QtCore import QObject, Signal, Slot, QTimer
from datetime import datetime

from domain.dto.device_info import (
    DeviceInfoDTO,
    DeviceNameDTO,
    DeviceOSDTO,
    DeviceBatteryDTO,
    DeviceStorageDTO,
)
from domain.dto.previous_device import PreviousDeviceDTO
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

    Signals:
        device_infos_updated (Signal[object]): Emitted with
            ``list[DeviceInfoDTO]`` whenever the current device's data changes.
        previous_devices_updated (Signal[list]): Emitted with
            ``list[PreviousDeviceDTO]`` when the full device history is loaded.
        device_connected (Signal): Emitted when the connectivity service
            reports a successful device connection.
        device_disconnected (Signal): Forwarded from the connectivity service
            after the device is disconnected.
    """

    device_infos_updated: Signal = Signal(object)
    previous_devices_updated: Signal = Signal(list)

    device_connected: Signal = Signal()
    device_disconnected: Signal = Signal()

    _TEN_MINUTES: int = 10 * 60 * 1000

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
        self._connectivity_service.device_disconnected.connect(self._on_device_disconnected)
        self._device_info_service.device_info_ready.connect(self._on_device_info_ready)
        self._device_info_service.device_fetched.connect(self._on_device_fetched)
        self._device_info_service.all_devices_fetched.connect(self._on_all_devices_fetched)

        # Start both services so DB reads (fetch_device_by_id / fetch_all_devices)
        # are available immediately at app startup, before any device connects.
        self._device_info_service.start()
        self._connectivity_service.start()

        # Mock device, until connectivity in phone side will be established
        self._device_info_service.save(
            DeviceEntity(
                id="1",
                name=str(uuid.uuid4()),
                os=str(uuid.uuid4()),
                tag="hey",
                battery_level=random.randint(0, 100),
                battery_charging=random.choice([True, False]),
                storage_used=random.randint(0, 1000),
                last_connected=datetime.strptime("2024-01-01", "%Y-%m-%d").date(),
                ip="127.0.0.1",
                storage_total=random.randint(1000, 10000),
            )
        )

        self._refresh_timer: QTimer = QTimer(self)
        self._refresh_timer.timeout.connect(self._request_device_info_refresh)
        self._refresh_timer.start(self._TEN_MINUTES)

        self._current_device_connected_id: str = "1"  # TODO: get this from the connectivity service when phone side works

    # ── Public API ────────────────────────────────────────────────────────────

    def load_device_info(self) -> None:
        """Request the current device from the service on a background thread.

        The result arrives asynchronously via :attr:`device_infos_updated`
        once :meth:`~services.device_info.DeviceInfoService.fetch_device_by_id`
        completes and :meth:`_on_device_fetched` handles the response.

        Emits:
            device_infos_updated: Asynchronously, with ``list[DeviceInfoDTO]``
                if the current device is found in the repository.
        """
        self._device_info_service.fetch_device_by_id(self._current_device_connected_id)

    def load_devices(self) -> None:
        """Request all stored devices from the service on a background thread.

        The result arrives asynchronously via :attr:`previous_devices_updated`
        once :meth:`~services.device_info.DeviceInfoService.fetch_all_devices`
        completes and :meth:`_on_all_devices_fetched` handles the response.

        Emits:
            previous_devices_updated: Asynchronously, with
                ``list[PreviousDeviceDTO]`` for every persisted device.
        """
        self._device_info_service.fetch_all_devices()

    def update_device_info(self) -> None:
        """Trigger a manual refresh of the current device's info.

        Delegates to the device-info service to re-read all device channels
        on a background thread.
        """
        self._request_device_info_refresh()

    # TODO: define what to do because as now cant listen and connect in the same time
    def connect_to_device(self, device: PreviousDeviceDTO) -> None:
        """Initiate a connection to a previously paired device.

        Args:
            device: The DTO of the device to connect to. Its ``id`` is passed
                to the connectivity service for identification.
        """
        self._connectivity_service.connect_to_device(device.id)

    def disconnect_device(self) -> None:
        """Disconnect the currently connected device via the connectivity service."""
        self._connectivity_service.stop()

    # ── Private helpers ────────────────────────────────────────────────────────

    def _request_device_info_refresh(self) -> None:
        """Delegate to the device-info service to fetch fresh device metadata."""
        self._device_info_service.fetch_device_info()

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot(object)
    def _on_device_info_ready(self, entity: DeviceEntity) -> None:
        """Handle a freshly assembled DeviceEntity from the device-info service.

        The entity is already persisted by :class:`~services.device_info.DeviceInfoService`
        before this signal fires, so the slot only needs to update the tracked
        ID and emit the DTO list so the view refreshes.

        Args:
            entity: The :class:`~entities.device_info.DeviceEntity` assembled
                from the TauSync channel reads.

        Emits:
            device_infos_updated: With the converted ``list[DeviceInfoDTO]``.
        """
        self._current_device_connected_id = entity.id
        self.device_infos_updated.emit(self._to_device_info_dtos(entity))

    @Slot(object)
    def _on_device_fetched(self, entity: DeviceEntity | None) -> None:
        """Handle the async result of :meth:`~services.device_info.DeviceInfoService.fetch_device_by_id`.

        Args:
            entity: The fetched :class:`~domain.entities.device_info.DeviceEntity`,
                or ``None`` if no match was found in the repository.

        Emits:
            device_infos_updated: With ``list[DeviceInfoDTO]`` if *entity* is
                not ``None``.
        """
        if entity is None:
            return
        self.device_infos_updated.emit(self._to_device_info_dtos(entity))

    @Slot(list)
    def _on_all_devices_fetched(self, devices: list[DeviceEntity]) -> None:
        """Handle the async result of :meth:`~services.device_info.DeviceInfoService.fetch_all_devices`.

        Args:
            devices: All :class:`~domain.entities.device_info.DeviceEntity`
                objects currently stored in the repository.

        Emits:
            previous_devices_updated: With the converted
                ``list[PreviousDeviceDTO]``.
        """
        dtos = [self._to_prev_device_dto(d) for d in devices]
        self.previous_devices_updated.emit(dtos)

    @Slot(object)
    def _on_entity_saved(self, entity: DeviceEntity) -> None:
        """Forward a repository save event to the view as a list of DTOs.

        Args:
            entity: The updated :class:`~entities.device_info.DeviceEntity`.

        Emits:
            device_infos_updated: With the converted ``list[DeviceInfoDTO]``.
        """
        self.device_infos_updated.emit(self._to_device_info_dtos(entity))

    @Slot()
    def _on_device_connected(self) -> None:
        """Handle a device connection event from the connectivity service.

        Emits ``device_connected`` to notify the view layer, then triggers a
        background refresh so the device info cards populate immediately.

        Emits:
            device_connected: To signal views that a device is now connected.
        """
        self._device_info_service.start()
        self._device_info_service.fetch_device_info()
        self.device_connected.emit()

    @Slot()
    def _on_device_disconnected(self):
        """Handle a device disconnection event from the connectivity service."""
        self._device_info_service.stop()
        self._connectivity_service.start()
        self.device_disconnected.emit()

    # ── Conversion ────────────────────────────────────────────────────────────

    @staticmethod
    def _to_device_info_dtos(entity: DeviceEntity) -> list[DeviceInfoDTO]:
        """Convert a DeviceEntity into one DTO per dashboard card.

        Args:
            entity: The connected device entity to convert.

        Returns:
            A list of ``DeviceInfoDTO`` subclass instances in display order:
            name → OS → battery → storage.
        """
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

    @staticmethod
    def _to_prev_device_dto(entity: DeviceEntity) -> PreviousDeviceDTO:
        """Convert a DeviceEntity into a PreviousDeviceDTO for the device list view.

        Args:
            entity: The :class:`~entities.device_info.DeviceEntity` to convert.

        Returns:
            A :class:`~dto.previous_device.PreviousDeviceDTO` with all
            fields populated from the entity.
        """
        return PreviousDeviceDTO(
            name=entity.name,
            os=entity.os,
            tag=entity.tag,
            last_connected=entity.last_connected,
            id=entity.id
        )

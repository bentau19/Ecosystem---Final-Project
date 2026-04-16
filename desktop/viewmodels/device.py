import random
import uuid
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot, QTimer
from datetime import datetime

from dto.device_info import (
    DeviceInfoDTO,
    DeviceNameDTO,
    DeviceOSDTO,
    DeviceBatteryDTO,
    DeviceStorageDTO,
)
from dto.previous_device import PreviousDeviceDTO
from entities.device_info import DeviceEntity
from repositories.device import DeviceRepository
from resources.paths import Icons
from services.connectivity import ConnectivityService


class DeviceViewModel(QObject):
    """ViewModel for the currently connected device's info dashboard.

    Reads a single ``DeviceEntity`` from the repository and exposes its fields
    to the view as a list of typed ``DeviceInfoDTO`` subclasses — one per
    dashboard card (name, OS, battery, storage).

    A periodic :class:`~PySide6.QtCore.QTimer` fires every 10 minutes to pull
    refreshed data from the connectivity service while a device is connected.

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
            repository: DeviceRepository,
            connectivity_service: ConnectivityService,
            parent: Optional[QObject] = None,
    ) -> None:
        """Initialize the ViewModel and wire up repository and service signals.

        Args:
            repository: The device repository used to persist and retrieve
                :class:`~entities.device_info.DeviceEntity` objects.
            connectivity_service: The service that manages the TauSync
                connection and emits device lifecycle signals.
            parent: Optional Qt parent object for memory management.
        """
        super().__init__(parent)
        self._device_repository: DeviceRepository = repository
        self._connectivity_service: ConnectivityService = connectivity_service

        self._connectivity_service.device_connected.connect(self._on_device_connected)
        self._connectivity_service.device_info_ready.connect(self._on_device_info_ready)
        self._connectivity_service.device_disconnected.connect(self.device_disconnected)

        # Mock device, until connectivity in phone side will be established
        self._device_repository.save(
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
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(self._TEN_MINUTES)

        self._current_device_connected_id: str = "1"  # TODO: get this from the connectivity service when phone side works

    def _refresh(self) -> None:
        """Refresh the view with the current device's info."""
        self._connectivity_service.get_device_info()

    # ── Public API ────────────────────────────────────────────────────────────

    def load_device_info(self) -> None:
        """Load the current device from the repository and emit ``device_infos_updated``.

        If the device ID does not match any stored entity, the method returns
        without emitting so the view retains its previous state.

        Emits:
            device_infos_updated: With ``list[DeviceInfoDTO]`` if the current
                device is found in the repository.
        """
        device_entity = self._device_repository.get_by_id(self._current_device_connected_id)
        if device_entity is None:
            return

        self.device_infos_updated.emit(self._to_device_info_dtos(entity=device_entity))

    def load_devices(self) -> None:
        """Load all previous devices from the repository and emit ``previous_devices_updated``.

        Emits:
            previous_devices_updated: With ``list[PreviousDeviceDTO]`` containing
                every device currently persisted in the repository.
        """
        previous_devices = self._device_repository.get_all()
        previous_device_dtos = [self._to_prev_device_dto(device) for device in previous_devices]
        self.previous_devices_updated.emit(previous_device_dtos)

    def update_device_info(self) -> None:
        """Trigger a manual refresh of the current device's info.

        Delegates to the connectivity service to re-read all device channels
        on a background thread.
        """
        self._refresh()

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
        self._connectivity_service.disconnect_device()

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot(object)
    def _on_device_info_ready(self, entity: DeviceEntity) -> None:
        """Handle a freshly assembled DeviceEntity from the connectivity service.

        Persists the entity to the repository, updates the tracked ID, and
        emits the DTO list so the view refreshes.

        Args:
            entity: The :class:`~entities.device_info.DeviceEntity` assembled
                from the TauSync channel reads.

        Emits:
            device_infos_updated: With the converted ``list[DeviceInfoDTO]``.
        """
        self._current_device_connected_id = entity.id
        self._device_repository.save(entity)
        self.device_infos_updated.emit(self._to_device_info_dtos(entity))

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
        self.device_connected.emit()
        self._refresh()

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

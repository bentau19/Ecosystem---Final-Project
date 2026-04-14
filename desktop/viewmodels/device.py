import random
import uuid
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot, QTimer

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

    Reads a single ``PreviousDeviceEntity`` from the repository and exposes
    its fields to the view as a list of typed ``DeviceInfoDTO`` subclasses —
    one per dashboard card (name, OS, battery, storage).

    Signals:
        device_infos_loaded:  Emitted with ``list[DeviceInfoDTO]`` when
            ``load_device_infos`` is called successfully.
        device_infos_updated: Emitted with ``list[DeviceInfoDTO]`` when the
            repository reports that the current device has changed.
        device_cleared:       Emitted when the current device is removed from
            the repository (e.g. on disconnect).
    """

    device_infos_updated: Signal = Signal(list)
    previous_devices_updated = Signal(list)

    device_connected: Signal = Signal()
    device_disconnected: Signal = Signal()

    def __init__(self, repository: DeviceRepository, connectivity_service: ConnectivityService,
                 parent: Optional[QObject] = None) -> None:
        """Initialize the ViewModel and wire up repository signals.

        Args:
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._device_repository: DeviceRepository = repository

        self._connectivity_service: ConnectivityService = connectivity_service
        self._connectivity_service.device_info_ready.connect(self.device_connected)
        self._connectivity_service.device_disconnected.connect(self.device_disconnected)

        self._device_repository.save(
            DeviceEntity(
                id="1",
                name=str(uuid.uuid4()),
                os=str(uuid.uuid4()),
                tag="hey",
                battery_level=random.randint(0, 100),
                battery_charging=random.choice([True, False]),
                storage_used=random.randint(0, 1000),
                last_connected="18-05-2025",
                ip="127.0.0.1",
                storage_total=random.randint(1000, 10000),
            )
        )
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(1)  # 10 min

        self._current_device_connected_id: str = "1"  # TODO: get this from the connectivity service when phone side works

    def _refresh(self) -> None:
        """Refresh the view with the current device's info."""
        # TODO: uncomment this line when phone side works as well
        self._connectivity_service.get_device_info()
        # self._connectivity_service.device_info_ready.emit(
        #     self._device_repository.get_by_id(self._current_device_connected_id))

    # ── Public API ────────────────────────────────────────────────────────────
    def load_device_info(self) -> None:
        """Load the current device from the repository and emit ``device_infos_loaded``.

        If no device is currently stored, the signal is emitted with an empty
        list so the view can handle the empty state explicitly.
        """
        device_entity = self._device_repository.get_by_id(self._current_device_connected_id)
        if device_entity is None:
            return

        self.device_infos_updated.emit(self._to_device_info_dtos(entity=device_entity))

    def load_devices(self):
        """Load all previous devices from the repository and emit ``previous_devices_updated``."""
        previous_devices = self._device_repository.get_all()
        previous_device_dtos = [self._to_prev_device_dto(device) for device in previous_devices]
        self.previous_devices_updated.emit(previous_device_dtos)

    def update_device_info(self) -> None:
        """Update the current device's info and emit ``device_infos_updated``."""
        self._refresh()

    # TODO: define what to do because as now cant listen and connect in the same time
    def connect_device(self, ip: str):
        self._connectivity_service.connect_to_device("192.168.68.112")
        pass

    def disconnect_device(self):
        self._connectivity_service.disconnect_device()

    # ── Slots ─────────────────────────────────────────────────────────────────
    #

    @Slot(object)
    def _on_device_info_ready(self, entity: DeviceEntity) -> None:
        self._device_repository.save(entity)
        self.device_infos_updated.emit(self._to_device_info_dtos(entity))
        pass

    @Slot(object)
    def _on_entity_saved(self, entity: DeviceEntity) -> None:
        """Forward a repository save event to the view as a list of DTOs.

        Args:
            entity: The updated ``PreviousDeviceEntity``.
        """
        self.device_infos_updated.emit(self._to_device_info_dtos(entity))

    # ── Conversion ────────────────────────────────────────────────────────────
    @staticmethod
    def _to_device_info_dtos(entity: DeviceEntity) -> list[DeviceInfoDTO]:
        """Convert a PreviousDeviceEntity into one DTO per dashboard card.

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
    def _to_prev_device_dto(entity: DeviceEntity):
        return PreviousDeviceDTO(
            name=entity.name,
            os=entity.os,
            tag=entity.tag,
            last_connected=entity.last_connected,
            ip=entity.ip
        )

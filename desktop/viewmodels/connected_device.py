from hmac import new

from PySide6.QtCore import QObject, Signal, Slot

from dto.connected_device import PreviousDeviceDTO
from entities.connected_device import PreviousDeviceEntity
from unit_tests import utils
from utils.repository_manger import repository_manager
from utils import network


class PreviousDeviceViewModel(QObject):
    """ViewModel for the previous-device list on the login screen.

    Converts PreviousDeviceEntity objects from the repository into
    PreviousDeviceDTO objects and exposes them to the view via Signals.

    Attributes:
        devices_loaded (Signal): Emitted with ``List[PreviousDeviceDTO]`` when
            ``load_devices`` is called.
        device_saved (Signal): Emitted with a ``PreviousDeviceDTO`` after the
            repository reports a successful save.
        device_deleted (Signal): Emitted with the deleted device ID (``str``)
            after the repository reports a deletion.
    """

    devices_loaded: Signal = Signal(list)
    device_saved: Signal = Signal(object)
    device_deleted: Signal = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the ViewModel and wire up repository signals.

        Args:
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._repo = repository_manager.previous_device_repository
        self._repo.entity_saved.connect(self._on_device_saved)
        self._repo.entity_deleted.connect(self._on_device_deleted)

        self._previous_device: dict[str, PreviousDeviceDTO] = {}

    def get_devices(self) -> list[PreviousDeviceDTO]:
        return list(self._previous_device.values())

    def load_devices(self) -> None:
        """Emit ``devices_loaded`` with all current previous devices as DTOs."""
        dtos: list[PreviousDeviceDTO] = [
            self._to_dto(entity) for entity in self._repo.get_all()
        ]
        for dto in dtos:
            self._previous_device[dto.id] = dto

        self.devices_loaded.emit(dtos)

    # def save_current_device(self) -> None:
    #     """Save a new device to the repository."""
    #     device: PreviousDeviceEntity =
    #     PreviousDeviceEntity(
    #         network.get_id(),
    #         network.get_name(),
    #         network.get_os_label(),
    #         network.get_tag(),
    #         network.get_status(),
    #         network.get_last_seen(),
    #         network.get_ip(),
    #     )
    #
    #     self._repo.save(PreviousDeviceEntity(**device.__dict__))

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _to_dto(entity: PreviousDeviceEntity) -> PreviousDeviceDTO:
        """Convert a PreviousDeviceEntity to a PreviousDeviceDTO.

        Args:
            entity: The entity to convert.

        Returns:
            A PreviousDeviceDTO with the same field values.
        """
        return PreviousDeviceDTO(
            id=entity.id,
            name=entity.name,
            os_label=entity.os_label,
            tag=entity.tag,
            icon_path=entity.icon_path,
            status=entity.status,
            last_seen=entity.last_seen,
            ip=entity.ip,
        )

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot(object)
    def _on_device_saved(self, entity: PreviousDeviceEntity) -> None:
        """Forward a repository ``device_saved`` event as a DTO signal.

        Args:
            entity: The saved device entity.
        """
        self.device_saved.emit(self._to_dto(entity))

    @Slot(str)
    def _on_device_deleted(self, device_id: str) -> None:
        """Forward a repository ``device_deleted`` event.

        Args:
            device_id: The ID of the deleted device.
        """
        self.device_deleted.emit(device_id)

from PySide6.QtCore import QObject, Signal, Slot

from dto.previous_device import PreviousDeviceDTO
from entities.previous_device import PreviousDeviceEntity
from repositories.interfaces.previous_device import IPreviousDeviceRepository
from utils.app_state import app_state


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
        self._repo: IPreviousDeviceRepository = app_state.previous_device_repository
        self._repo.device_saved.connect(self._on_device_saved)
        self._repo.device_deleted.connect(self._on_device_deleted)

        self._previous_device: dict[str, PreviousDeviceDTO] = {}

    def get_devices(self) -> list[PreviousDeviceDTO]:
        return list(self._previous_device.values())

    # ── Public API ────────────────────────────────────────────────────────────

    def load_devices(self) -> None:
        """Emit ``devices_loaded`` with all current previous devices as DTOs."""
        dtos: list[PreviousDeviceDTO] = [
            self._to_dto(entity) for entity in self._repo.get_all()
        ]
        for dto in dtos:
            self._previous_device[dto.id] = dto

        self.devices_loaded.emit(dtos)

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
            icon_color=entity.icon_color,
            status=entity.status,
            last_seen=entity.last_seen,
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

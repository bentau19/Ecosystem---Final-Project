from PySide6.QtCore import QObject, Signal

from entities.previous_device import PreviousDeviceEntity
from repositories.interfaces.previous_device import IPreviousDeviceRepository
from stores.interfaces.base import IStore
from stores.previous_device import PreviousDeviceStore
from utils.meta import ABCQObjectMeta


class PreviousDeviceRepository(IPreviousDeviceRepository, QObject, metaclass=ABCQObjectMeta):
    """Repository for previously connected devices shown on the login screen.

    Loads device data from a JSON-backed store on construction and keeps an
    in-memory cache that is flushed to disk on every mutation.

    Attributes:
        device_saved (Signal): Emitted with the saved PreviousDeviceEntity after
            ``save`` completes successfully.
        device_deleted (Signal): Emitted with the deleted device ID after
            ``delete`` completes.
    """

    device_saved: Signal = Signal(object)
    device_deleted: Signal = Signal(str)

    def __init__(
        self,
        store: IStore = PreviousDeviceStore(),
        parent: QObject | None = None,
    ) -> None:
        """Initialize the repository and eagerly load data from the store.

        Args:
            store: The backing store used for file I/O.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._store: IStore = store
        self._devices: dict[str, PreviousDeviceEntity] = self._store.load()

    def load(self) -> dict[str, PreviousDeviceEntity]:
        """Reload all devices from the backing store.

        Returns:
            Mapping of device ID → PreviousDeviceEntity.
        """
        self._devices = self._store.load()
        return self._devices

    def get_by_id(self, id: str) -> PreviousDeviceEntity | None:
        """Return the device with the given ID, or ``None`` if absent.

        Args:
            id: The unique device identifier.

        Returns:
            The matching PreviousDeviceEntity, or ``None``.
        """
        return self._devices.get(id)

    def get_all(self) -> list[PreviousDeviceEntity]:
        """Return all stored previous devices.

        Returns:
            A list of all PreviousDeviceEntity objects.
        """
        return list(self._devices.values())

    def save(self, entity: PreviousDeviceEntity) -> None:
        """Insert or update a device and flush to disk.

        Emits ``device_saved`` with the entity after the store write.

        Args:
            entity: The device to persist.
        """
        self._devices[entity.id] = entity
        self._store.save(self._devices)
        self.device_saved.emit(entity)

    def delete(self, id: str) -> None:
        """Remove a device by ID and flush to disk.

        Emits ``device_deleted`` with the device ID regardless of whether the
        ID was present in the cache.

        Args:
            id: The unique device identifier to remove.
        """
        if id in self._devices:
            del self._devices[id]
            self._store.save(self._devices)
        self.device_deleted.emit(id)

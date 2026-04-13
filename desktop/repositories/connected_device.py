from PySide6.QtCore import QObject, Signal

from entities.connected_device import PreviousDeviceEntity
from repositories.interfaces.base import IRepository
from stores.interfaces.base import IStore
from stores.connected_device import PreviousDeviceStore
from utils.meta import ABCQObjectMeta


class PreviousDeviceRepository(IRepository[PreviousDeviceEntity, str], QObject, metaclass=ABCQObjectMeta):
    """Repository for previously connected devices shown on the login screen.

    Implements the singleton pattern so that a single shared instance is used
    throughout the application.  Data is eagerly loaded from the backing store
    on first construction and kept in an in-memory cache; every mutation
    flushes the full cache back to disk.

    Signals:
        entity_saved:   Emitted with the saved PreviousDeviceEntity after a
            successful ``save`` call.
        entity_deleted: Emitted with the deleted device ID after ``delete``
            completes (regardless of whether the ID was present in the cache).
    """

    entity_saved: Signal = Signal(object)
    entity_deleted: Signal = Signal(str)

    def __init__(
            self,
            store: IStore = PreviousDeviceStore(),
            parent: QObject | None = None,
    ) -> None:
        """Initialize the repository and eagerly load data from the store.

        Guarded by ``_initialized`` so that the singleton body only runs once
        even if the constructor is called multiple times.

        Args:
            store: The backing store used for file I/O.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._store: IStore = store
        self._devices: dict[str, PreviousDeviceEntity] = {}
        self._load()

    def _load(self) -> dict[str, PreviousDeviceEntity]:
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

        Args:
            entity: The device to persist.

        Emits:
            device_saved: With the entity after the store write.
        """
        self._devices[entity.id] = entity
        self._store.save(self._devices)
        self.entity_saved.emit(entity)

    def delete(self, id: str) -> None:
        """Remove a device by ID and flush to disk if the ID was present.

        The store is only written when the ID existed in the cache — if nothing
        changed in memory there is nothing new to persist.

        Args:
            id: The unique device identifier to remove.

        Emits:
            device_deleted: With the device ID regardless of whether it was
                present in the cache.
        """
        if id in self._devices:
            del self._devices[id]
            self._store.save(self._devices)
        self.entity_deleted.emit(id)

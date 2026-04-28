from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from PySide6.QtCore import Signal

T = TypeVar('T')
K = TypeVar('K')


class IRepository(ABC, Generic[T, K]):
    """Abstract base interface for all repositories.

    Repositories are responsible for storing and retrieving domain entities.
    Concrete implementations manage both an in-memory cache and a persistent
    backing store.

    Signals (annotations only — concrete class must define the actual Signal):
        entity_saved:   Emitted with the saved entity after a successful save.
        entity_deleted: Emitted with the entity key after a successful delete.
    """

    entity_saved: Signal
    entity_deleted: Signal

    @abstractmethod
    def get_by_id(self, id: K) -> T | None:
        """Return the entity with the given ID, or ``None`` if absent.

        Args:
            id: The unique identifier of the entity.

        Returns:
            The entity with the given ID, or ``None`` if it does not exist.
        """
        ...

    @abstractmethod
    def get_all(self) -> list[T]:
        """Return all entities stored in the repository.

        Returns:
            A list of all entities.
        """
        ...

    @abstractmethod
    def save(self, entity: T) -> None:
        """Persist an entity to the repository.

        Args:
            entity: The entity to save (insert or update).
        """
        ...

    @abstractmethod
    def delete(self, id: K) -> None:
        """Remove an entity from the repository.

        Args:
            id: The unique identifier of the entity to delete.
        """
        ...

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar('T')
K = TypeVar('K')


class IRepository(ABC, Generic[T, K]):
    """
    Interface for a repository.

    Repositories are responsible for storing and retrieving entities.
    """

    @abstractmethod
    def get_by_id(self, id: K) -> T | None:
        """
        Get an entity by its ID.

        Args:
            id: The ID of the entity.

        Returns:
            The entity with the given ID, or None if it does not exist.
        """
        ...

    @abstractmethod
    def get_all(self) -> list[T]:
        """
        Get all entities stored in the repository.

        Returns:
            A list of all entities.
        """
        ...

    @abstractmethod
    def save(self, entity: T) -> None:
        """
       save entity to the repository.

        Args:
            entity: The entity to add.
        """
        ...

    @abstractmethod
    def delete(self, id: K) -> None:
        """
        Delete an entity from the repository.

        Args:
            id: The ID of the entity to delete.
        """
        ...

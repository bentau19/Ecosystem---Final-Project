from abc import ABC, abstractmethod
from typing import TypeVar, Generic

T = TypeVar('T')
K = TypeVar('K')


class IStore(ABC, Generic[T, K]):
    """
    Interface for a store.

    A store is responsible for loading and saving data.
    """

    @abstractmethod
    def load(self) -> T:
        """
        Load data from the store.

        Returns:
            The loaded data.
        """
        ...

    @abstractmethod
    def save(self, data: K) -> None:
        """
        Save data to the store.

        Args:
            data: The data to save.
        """
        ...
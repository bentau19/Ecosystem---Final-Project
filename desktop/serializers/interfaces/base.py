from abc import abstractmethod, ABC
from typing import Generic, TypeVar, Any, Dict

T = TypeVar('T')
K = TypeVar('K')


class ISerializer(ABC, Generic[T, K]):
    @abstractmethod
    def serialize(self, data: T) -> K:
        """
        Serialize the given data into the specified format.

        Args:
            data: The data to serialize.

        Returns:
            The serialized data.
        """
        ...

    @abstractmethod
    def deserialize(self, data: K) -> T:
        """
        Deserialize the given data from the specified format.

        Args:
            data: The data to deserialize.

        Returns:
            The deserialized data.
        """
        ...
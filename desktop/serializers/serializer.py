from abc import abstractmethod, ABC
from typing import Generic, TypeVar

T = TypeVar('T')
K = TypeVar('K')


class ISerializer(ABC, Generic[T, K]):
    """Abstract base for all entity serializers.

    Defines a symmetric contract: ``serialize`` converts a domain entity into
    a storage/transport representation, and ``deserialize`` reconstructs the
    entity from that representation.

    Type Parameters:
        T: The domain entity type (e.g. ``DeviceEntity``).
        K: The serialized form type (e.g. ``tuple``, ``dict``).
    """

    @abstractmethod
    def serialize(self, data: T) -> K:
        """Convert a domain entity into its serialized representation.

        Args:
            data: The entity to serialize.

        Returns:
            The serialized form ready for storage or transport.
        """
        ...

    @abstractmethod
    def deserialize(self, data: K) -> T:
        """Reconstruct a domain entity from its serialized representation.

        Args:
            data: The serialized form as returned by the backing store.

        Returns:
            The reconstructed domain entity.
        """
        ...

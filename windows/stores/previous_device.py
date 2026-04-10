import json
import os

from entities.previous_device import PreviousDeviceEntity
from serializers.interfaces.base import ISerializer
from serializers.previous_device import PreviousDeviceSerializer
from stores.interfaces.base import IStore


class PreviousDeviceStore(IStore[dict[str, PreviousDeviceEntity], dict[str, PreviousDeviceEntity]]):
    """Persists PreviousDeviceEntity objects as a JSON file.

    Implements raw file I/O; all JSON ↔ entity conversion is delegated to the
    injected serializer.
    """

    def __init__(
        self,
        serializer: ISerializer = PreviousDeviceSerializer(),
        json_path: str = "data/previous_devices.json",
    ) -> None:
        """Initialize the store.

        Args:
            serializer: Serializer used to convert between entities and raw dicts.
            json_path: Path to the backing JSON file.
        """
        self._json_path = json_path
        self._serializer = serializer

    def load(self) -> dict[str, PreviousDeviceEntity]:
        """Load all previous devices from disk.

        Returns:
            Mapping of device ID → PreviousDeviceEntity.  Returns an empty dict
            when the backing file does not yet exist.
        """
        if not os.path.exists(self._json_path):
            return {}
        with open(self._json_path, encoding="utf-8") as f:
            return self._serializer.deserialize(json.load(f))

    def save(self, data: dict[str, PreviousDeviceEntity]) -> None:
        """Persist all previous devices to disk.

        Args:
            data: Mapping of device ID → PreviousDeviceEntity to write.
        """
        with open(self._json_path, "w", encoding="utf-8") as f:
            json.dump(self._serializer.serialize(data), f, indent=2)

import json
import os
from typing import Dict

from entities.device_info import DeviceBaseInfoEntity, DeviceType
from serializers.device_info import DeviceInfoSerializer
from serializers.interfaces.base import ISerializer
from stores.interfaces.base import IStore


class DeviceInfoStore(IStore[Dict[DeviceType, DeviceBaseInfoEntity], Dict[DeviceType, DeviceBaseInfoEntity]]):
    """
    Store for device information.
    """

    def __init__(
        self, serializer: ISerializer = DeviceInfoSerializer(), json_path: str = "data/device_info.json"
    ) -> None:
        """
        Initialize the device info store.

        Args:
            serializer: The serializer for device info entities.
            json_path: The path to the JSON file.
        """
        self._json_path = json_path
        self._serializer = serializer

    def load(self) -> Dict[DeviceType, DeviceBaseInfoEntity]:
        """
        Load device info data from a JSON file.

        Returns:
            The loaded device info data.
        """
        if not os.path.exists(self._json_path):
            return {}
        with open(self._json_path) as f:
            return self._serializer.deserialize(json.load(f))

    def save(self, data: Dict[DeviceType, DeviceBaseInfoEntity]) -> None:
        """
        Save device info data to a JSON file.

        Args:
            data: The device info data to save.
        """
        with open(self._json_path, "w") as f:
            serialized_data = self._serializer.serialize(data)
            json.dump(serialized_data, f, indent=2)
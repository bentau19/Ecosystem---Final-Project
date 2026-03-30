import json
import os
from typing import Dict

from entities.tool import ToolEntity
from serializers.interfaces.base import ISerializer
from serializers.tool import ToolSerializer
from stores.interfaces.base import IStore


class ToolStore(IStore[Dict[str, ToolEntity], Dict[str, ToolEntity]]):
    """
    Store for tool information.
    """

    def __init__(self, serializer: ISerializer = ToolSerializer(), json_path: str = "data/tool.json") -> None:
        """
        Initialize the tool store.

        Args:
            serializer: The serializer to use.
            json_path: The path to the JSON file.
        """
        self._json_path = json_path
        self._serializer = serializer

    def load(self) -> Dict[str, ToolEntity]:
        """
        Load tool information from the JSON file.

        Returns:
            The loaded tool information.
        """
        if not os.path.exists(self._json_path):
            return {}
        with open(self._json_path) as f:
            return self._serializer.deserialize(json.load(f))

    def save(self, data: Dict[str, ToolEntity]) -> None:
        """
        Save tool information to the JSON file.

        Args:
            data: The tool information to save.
        """
        with open(self._json_path, "w") as f:
            print("Saving tool information to JSON file...")
            print(self._serializer.serialize(data))
            json.dump(self._serializer.serialize(data), f, indent=2)
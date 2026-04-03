from typing import Dict
from dataclasses import asdict

from entities.tool import ToolEntity
from serializers.interfaces.base import ISerializer


class ToolSerializer(ISerializer[Dict[str, ToolEntity], dict]):
    """
    Serializes and deserializes ToolEntity objects to and from dictionaries.

    Methods:
        serialize(data: Dict[str, ToolEntity]) -> dict:
            Serializes a dictionary of ToolEntity objects to a dictionary.
        deserialize(data: dict) -> Dict[str, ToolEntity]:
            Deserializes a dictionary to a dictionary of ToolEntity objects.
    """

    def serialize(self, data: Dict[str, ToolEntity]) -> dict:
        """
        Serializes a dictionary of ToolEntity objects to a dictionary.

        Args:
            data: A dictionary of ToolEntity objects.

        Returns:
            A dictionary representation of the ToolEntity objects.
        """
        return {k: asdict(v) for k, v in data.items()}

    def deserialize(self, data: dict) -> Dict[str, ToolEntity]:
        """
        Deserializes a dictionary to a dictionary of ToolEntity objects.

        Args:
            data: A dictionary representation of ToolEntity objects.

        Returns:
            A dictionary of ToolEntity objects.
        """
        return {k: ToolEntity(**v) for k, v in data.items()}

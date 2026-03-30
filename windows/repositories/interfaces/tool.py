from abc import ABC, abstractmethod
from typing import List, Optional

from PySide6.QtCore import Signal

from entities.tool import ToolEntity
from repositories.interfaces.base import IRepository


class IToolRepository(IRepository[ToolEntity, str], ABC):
    """Interface for a tool repository.

    Attributes:
        tool_saved (Signal): Emitted when a tool is saved.
        tool_deleted (Signal): Emitted when a tool is deleted.
    """

    tool_saved: Signal
    tool_deleted: Signal

    @abstractmethod
    def get_by_id(self, id: str) -> Optional[ToolEntity]:
        """
        Get a tool by its ID.

        Args:
            id: The ID of the tool.

        Returns:
            The tool with the given ID, or None if it does not exist.
        """
        ...

    @abstractmethod
    def get_all_enabled(self) -> List[ToolEntity]:
        """
        Get all enabled tools.

        Returns:
            A list of all enabled tools.
        """
        ...

    @abstractmethod
    def get_all(self) -> List[ToolEntity]:
        """
        Get all tools.

        Returns:
            A list of all tools.
        """
        ...

    @abstractmethod
    def save(self, entity: ToolEntity) -> None:
        """
        save a tool to the repository.

        Args:
            entity: The tool to add.
        """
        ...

    @abstractmethod
    def delete(self, id: str) -> None:
        """
        Delete a tool from the repository.

        Args:
            id: The ID of the tool to delete.
        """
        ...

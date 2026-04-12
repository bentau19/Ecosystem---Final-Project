from abc import ABC, abstractmethod

from PySide6.QtCore import Signal

from entities.tool import ToolEntity
from repositories.interfaces.base import IRepository


class IToolRepository(IRepository[ToolEntity, str], ABC):
    """Abstract interface for the tool repository.

    Signals:
        tool_saved: Emitted when a tool is saved.
        tool_deleted: Emitted when a tool is deleted.
    """

    tool_saved: Signal
    tool_deleted: Signal

    @abstractmethod
    def get_by_id(self, id: str) -> ToolEntity | None:
        """Return the tool with the given ID, or ``None`` if absent.

        Args:
            id: The unique identifier of the tool.

        Returns:
            The ToolEntity with the given ID, or ``None`` if not found.
        """
        ...

    @abstractmethod
    def get_all_enabled(self) -> list[ToolEntity]:
        """Return all enabled tools.

        Returns:
            A list of ToolEntity objects where ``is_enabled`` is ``True``.
        """
        ...

    @abstractmethod
    def get_all(self) -> list[ToolEntity]:
        """Return all stored tools.

        Returns:
            A list of all ToolEntity objects.
        """
        ...

    @abstractmethod
    def save(self, entity: ToolEntity) -> None:
        """Persist a tool to the repository.

        Args:
            entity: The tool to save.
        """
        ...

    @abstractmethod
    def delete(self, id: str) -> None:
        """Remove a tool from the repository.

        Args:
            id: The unique identifier of the tool to delete.
        """
        ...

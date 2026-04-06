from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from entities.tool import ToolEntity
from repositories.interfaces.tool import IToolRepository
from stores.interfaces.base import IStore
from stores.tool import ToolStore
from utils.meta import ABCQObjectMeta


class ToolRepository(IToolRepository, QObject, metaclass=ABCQObjectMeta):
    """Repository for tools.

    Attributes:
        tool_saved (Signal): Emitted when a tool is added.
        tool_deleted (Signal): Emitted when a tool is deleted.
    """

    tool_saved: Signal = Signal(object)

    tool_deleted: Signal = Signal(str)

    def __init__(self, store: IStore = ToolStore(), parent: QObject | None = None) -> None:
        """
        Initialize the tool repository.

        Args:
            parent: The parent QObject.
        """
        super().__init__(parent)

        self._store: IStore = store
        self._tools: Dict[str, ToolEntity] = self.load()


    def load(self) -> Dict[str, ToolEntity]:
        """
        Load the tools from the repository.

        Returns:
            Dict[str, ToolEntity]: A dictionary mapping tool names to ToolEntity objects.
        """
        return self._store.load()

    def save(self, entity: ToolEntity) -> None:
        """
        Save a tool to the repository and emit the tool_saved signal if successful.

        Args:
            entity (ToolEntity): The tool to save.

        Raises:
            ValueError: If a tool with the same title already exists.
        """
        if entity.title in self._tools:
            raise ValueError(f"Tool with title '{entity.title}' already exists.")
        self._tools[entity.title] = entity
        self.tool_saved.emit(entity)
        self._store.save(self._tools)

    def get_by_id(self, id: str) -> Optional[ToolEntity]:
        """
        Get a tool by its ID.

        Args:
            id: The ID of the tool.

        Returns:
            The tool with the given ID, or None if it does not exist.
        """
        if id not in self._tools:
            return None
        return self._tools[id]

    def get_all(self) -> List[ToolEntity]:
        """
        Get all tools.

        Returns:
            A list of all tools.
        """
        return list(self._tools.values())

    def get_all_enabled(self) -> List[ToolEntity]:
        """
        Get all enabled tools.

        Returns:
            A list of all enabled tools.
        """
        return [tool for tool in self._tools.values() if tool.is_enabled]

    def delete(self, id: str) -> None:
        """
        Delete a tool from the repository.

        Args:
            id: The ID of the tool to delete.
        """
        if id in self._tools:
            del self._tools[id]
        self.tool_deleted.emit(id)


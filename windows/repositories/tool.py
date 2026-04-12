from PySide6.QtCore import QObject, Signal

from entities.tool import ToolEntity
from repositories.interfaces.tool import IToolRepository
from stores.interfaces.base import IStore
from stores.tool import ToolStore
from utils.meta import ABCQObjectMeta


class ToolRepository(IToolRepository, QObject, metaclass=ABCQObjectMeta):
    """Repository for tool entities.

    Implements the singleton pattern so that a single shared instance is used
    throughout the application.  Data is eagerly loaded from the backing store
    on first construction and kept in an in-memory cache; save mutations flush
    the full cache back to disk.

    Signals:
        tool_saved: Emitted with the saved ToolEntity after a successful
            ``save`` call.
        tool_deleted: Emitted with the tool ID string after a ``delete`` call.
    """


    tool_saved: Signal = Signal(object)
    tool_deleted: Signal = Signal(str)

    def __init__(self, store: IStore = ToolStore(), parent: QObject | None = None) -> None:
        """Initialize the tool repository.

        Guarded by ``_initialized`` so that the singleton body only runs once
        even if the constructor is called multiple times.

        Args:
            store: Backing store used for file I/O.  Defaults to a fresh
                ``ToolStore`` instance.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._store: IStore = store
        self._tools: dict[str, ToolEntity] = self.load()
        self._initialized = True

    def load(self) -> dict[str, ToolEntity]:
        """Load tools from the backing store.

        Returns:
            A dictionary mapping tool titles to ToolEntity objects.
        """
        return self._store.load()

    def save(self, entity: ToolEntity) -> None:
        """Insert a new tool and flush to disk.

        Args:
            entity: The tool to save.

        Raises:
            ValueError: If a tool with the same title already exists.

        Emits:
            tool_saved: With the saved entity after the store write.
        """
        if entity.title in self._tools:
            raise ValueError(f"Tool with title '{entity.title}' already exists.")
        self._tools[entity.title] = entity
        self.tool_saved.emit(entity)
        self._store.save(self._tools)

    def get_by_id(self, id: str) -> ToolEntity | None:
        """Return the tool with the given ID, or ``None`` if absent.

        Args:
            id: The tool title used as the dictionary key.

        Returns:
            The matching ToolEntity, or ``None`` if not found.
        """
        if id not in self._tools:
            return None
        return self._tools[id]

    def get_all(self) -> list[ToolEntity]:
        """Return all stored tools.

        Returns:
            A list of all ToolEntity objects.
        """
        return list(self._tools.values())

    def get_all_enabled(self) -> list[ToolEntity]:
        """Return only tools that are currently enabled.

        Returns:
            A list of ToolEntity objects where ``is_enabled`` is ``True``.
        """
        return [tool for tool in self._tools.values() if tool.is_enabled]

    def delete(self, id: str) -> None:
        """Remove a tool by ID and emit the deleted signal.

        Args:
            id: The tool title to remove.

        Emits:
            tool_deleted: With the tool ID regardless of whether it was
                present in the cache.
        """
        if id in self._tools:
            del self._tools[id]
        self.tool_deleted.emit(id)

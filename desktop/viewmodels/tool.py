from PySide6.QtCore import QObject, Signal, Slot

from domain.dto.tool import ToolDTO
from domain.entities.tool import ToolEntity
from repositories.tool import ToolRepository


class ToolViewModel(QObject):
    """
    ViewModel for Tools.

    Attributes:
        tool_updated (Signal): Emitted when a tool is updated.
        tool_added (Signal): Emitted when a tool is added.
        tool_deleted (Signal): Emitted when a tool is deleted.
        tools_loaded (Signal): Emitted when tools are loaded.
        tool_count_changed (Signal): Emitted when the number of tools changes.
    """

    tool_updated: Signal = Signal(object)
    tool_added: Signal = Signal(object)
    tool_deleted: Signal = Signal(str)
    tools_loaded: Signal = Signal(list)
    tool_count_changed: Signal = Signal(int)

    def __init__(self, tool_repository: ToolRepository, parent: QObject | None = None) -> None:
        """Initialize the ToolViewModel.

        Populates the in-memory enabled-tool list from the repository on
        construction and wires repository signals for ongoing mutations.

        Args:
            tool_repository: The repository used to read and persist tool data.
            parent: Optional Qt parent object for memory management.
        """
        super().__init__(parent)

        self._repo = tool_repository
        self._enabled_tools: list[ToolDTO] = [
            self._convert_to_dto(tool) for tool in self._repo.get_all_enabled()
        ]

        self._repo.entity_saved.connect(self._on_tool_added)
        self._repo.entity_deleted.connect(self._on_tool_deleted)

    @staticmethod
    def _convert_to_dto(entity: ToolEntity) -> ToolDTO:
        """
        Convert a ToolEntity to a ToolDTO.

        Args:
            entity (ToolEntity): The ToolEntity to convert.

        Returns:
            ToolDTO: The converted ToolDTO.
        """
        return ToolDTO(
            entity.title,
            entity.description,
            entity.icon_path,
            entity.is_enabled,
        )

    @Slot(ToolEntity)
    def _on_tool_updated(self, entity: ToolEntity) -> None:
        """
        Handle when a tool is updated.

        Args:
            entity (ToolEntity): The updated tool.
        """
        tool = self._convert_to_dto(entity)
        self.tool_updated.emit(tool.title)
        self._enabled_tools = [
            self._convert_to_dto(tool) for tool in self._repo.get_all_enabled()
        ]

    @Slot(ToolEntity)
    def _on_tool_added(self, entity: ToolEntity) -> None:
        """
        Handle when a tool is added.

        Args:
            entity (ToolEntity): The added tool.
        """
        tool = self._convert_to_dto(entity)
        self.tool_added.emit(tool)
        self._enabled_tools.append(tool)
        self.tool_count_changed.emit(len(self._enabled_tools))

    @Slot(str)
    def _on_tool_deleted(self, id: str) -> None:
        """
        Handle when a tool is deleted.

        Args:
            id (str): The ID of the deleted tool.
        """
        self._enabled_tools = [
            self._convert_to_dto(tool) for tool in self._repo.get_all_enabled()
        ]

        self.tool_count_changed.emit(len(self._enabled_tools))
        self.tool_deleted.emit(id)

    def load_enabled_tools(self) -> None:
        """Emit the current enabled-tool list and the total count.

        Emits:
            tools_loaded: With the in-memory ``list[ToolDTO]`` of enabled tools.
            tool_count_changed: With the number of enabled tools as an ``int``.
        """
        self.tools_loaded.emit(self._enabled_tools)
        self.tool_count_changed.emit(len(self._enabled_tools))

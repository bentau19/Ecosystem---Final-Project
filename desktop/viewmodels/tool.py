from PySide6.QtCore import QObject, Signal, Slot

from domain.dto.tool import ToolDTO
from domain.entities.tool import ToolEntity
from services.tool import ToolService


class ToolViewModel(QObject):
    """ViewModel for Tools.

    Translates :class:`~services.tool.ToolService` signals into view-ready
    DTOs and maintains the in-memory enabled-tool list.

    Signals:
        tool_updated (Signal[object]): Emitted when a tool is updated.
        tool_added (Signal[object]): Emitted with the new :class:`~domain.dto.tool.ToolDTO`
            when a tool is added.
        tool_deleted (Signal[str]): Emitted with the tool title when a tool is deleted.
        tools_loaded (Signal[list]): Emitted with the current enabled-tool list.
        tool_count_changed (Signal[int]): Emitted with the new count when the
            number of enabled tools changes.
    """

    tool_updated: Signal = Signal(object)
    tool_added: Signal = Signal(object)
    tool_deleted: Signal = Signal(str)
    tools_loaded: Signal = Signal(list)
    tool_count_changed: Signal = Signal(int)

    def __init__(self, tool_service: ToolService, parent: QObject | None = None) -> None:
        """Initialize the ToolViewModel.

        Populates the in-memory enabled-tool list from the service on
        construction and wires service signals for ongoing mutations.

        Args:
            tool_service: The :class:`~services.tool.ToolService` used to read
                tool data and receive mutation notifications.
            parent: Optional Qt parent object for memory management.
        """
        super().__init__(parent)

        self._tool_service: ToolService = tool_service
        self._enabled_tools: list[ToolDTO] = []

        self._tool_service.tool_added.connect(self._on_tool_added)
        self._tool_service.tool_deleted.connect(self._on_tool_deleted)
        self._tool_service.all_enabled_tools_fetched.connect(self._on_all_enabled_fetched)

        # Start the service so fetch_all_enabled() requests are accepted, then
        # kick off the initial load so the view populates without blocking the
        # GUI thread.
        self._tool_service.start()
        self._tool_service.fetch_all_enabled()

    @staticmethod
    def _convert_to_dto(entity: ToolEntity) -> ToolDTO:
        return ToolDTO(
            entity.title,
            entity.description,
            entity.icon_path,
            entity.is_enabled,
        )

    @Slot(ToolEntity)
    def _on_tool_updated(self, entity: ToolEntity) -> None:
        tool = self._convert_to_dto(entity)
        self.tool_updated.emit(tool.title)
        # Refresh the enabled-tool list asynchronously; the result arrives via
        # _on_all_enabled_fetched which updates _enabled_tools and emits
        # tool_count_changed.
        self._tool_service.fetch_all_enabled()

    @Slot(ToolEntity)
    def _on_tool_added(self, entity: ToolEntity) -> None:
        tool = self._convert_to_dto(entity)
        self.tool_added.emit(tool)
        self._enabled_tools.append(tool)
        self.tool_count_changed.emit(len(self._enabled_tools))

    @Slot(str)
    def _on_tool_deleted(self, id: str) -> None:
        # Notify the view immediately so it can remove the card without waiting
        # for the async DB refresh.
        self.tool_deleted.emit(id)
        # Refresh the enabled-tool list asynchronously; the result arrives via
        # _on_all_enabled_fetched which updates _enabled_tools and emits
        # tool_count_changed.
        self._tool_service.fetch_all_enabled()

    @Slot(list)
    def _on_all_enabled_fetched(self, tools: list[ToolEntity]) -> None:
        self._enabled_tools = [self._convert_to_dto(t) for t in tools]
        self.tool_count_changed.emit(len(self._enabled_tools))

    def load_enabled_tools(self) -> None:
        """Emit the current enabled-tool list and the total count.

        Emits:
            tools_loaded: With the in-memory ``list[ToolDTO]`` of enabled tools.
            tool_count_changed: With the number of enabled tools as an ``int``.
        """
        self.tools_loaded.emit(self._enabled_tools)
        self.tool_count_changed.emit(len(self._enabled_tools))

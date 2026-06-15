from PySide6.QtCore import QObject, Signal, Slot

from domain.dto.tool import ToolDTO
from domain.entities.tool import ToolEntity
from services.tool import ToolService


class ToolViewModel(QObject):
    """ViewModel for Tools.

    Translates :class:`~services.tool.ToolService` signals into view-ready
    DTOs and maintains the in-memory enabled-tool list.

    Signals:
        tools_loaded (Signal[list]): Emitted with the current ``list[ToolDTO]``
            of enabled tools — fires both on async fetch completion and on an
            explicit :meth:`load_enabled_tools` call.
        tools_changed (Signal[object]): Emitted alongside ``tools_loaded``
            whenever the enabled-tool list changes, for subscribers that do
            not need to distinguish initial load from refresh.
    """

    tools_changed: Signal = Signal(object)
    tools_loaded: Signal = Signal(list)

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

        self._tool_service.all_enabled_tools_fetched.connect(self._on_all_enabled_fetched)

        # Start the service so fetch_all_enabled() requests are accepted, then
        # kick off the initial load so the view populates without blocking the
        # GUI thread.
        self._tool_service.start()
        self._tool_service.fetch_all_enabled()

    @staticmethod
    def _convert_to_dto(entity: ToolEntity) -> ToolDTO:
        # Map entity fields to the flat DTO the view layer consumes.
        return ToolDTO(
            entity.title,
            entity.description,
            entity.icon_path,
            entity.is_enabled,
        )

    @Slot(list)
    def _on_all_enabled_fetched(self, tools: list[ToolEntity]) -> None:
        # Replace the in-memory list and notify all subscribers (grid + any count badges).
        self._enabled_tools: list[ToolDTO] = [self._convert_to_dto(t) for t in tools]
        self.tools_loaded.emit(self._enabled_tools)
        self.tools_changed.emit(self._enabled_tools)

    def load_enabled_tools(self) -> None:
        """Emit the current enabled-tool list to all subscribers.

        Emits:
            tools_loaded: With the in-memory ``list[ToolDTO]`` of enabled tools.
            tools_changed: With the same ``list[ToolDTO]``, for subscribers that
                only care about change notifications.
        """
        self.tools_loaded.emit(self._enabled_tools)
        self.tools_changed.emit(self._enabled_tools)

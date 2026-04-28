from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QLabel, QWidget

from dto.tool import ToolDTO
from layouts.flow_layout import FlowLayout
from resources.colors import Palette
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.repository_manger import repository_manager
from utils.styles import load_stylesheet
from viewmodels.tool import ToolViewModel
from views.widgets.dashboard.tool_card import ToolCard


class ToolsGrid(QWidget):
    """Flow-layout grid of enabled :class:`~views.widgets.dashboard.tool_card.ToolCard` widgets.

    Loads the enabled tool list from a :class:`~viewmodels.tool.ToolViewModel`
    on construction and renders one card per tool using a
    :class:`~layouts.flow_layout.FlowLayout` that wraps automatically to fill
    the available width.
    """

    def __init__(self, card_width: int = 300, card_height: int = 170, parent: QWidget | None = None) -> None:
        """Initialize the ToolsGrid widget.

        Args:
            card_width: Width applied to each tool card. Defaults to 300.
            card_height: Fixed height applied to each tool card. Defaults to 170.
            parent: Parent widget. Defaults to None.
        """
        super().__init__(parent)

        self._card_width: int = card_width
        self._card_height: int = card_height

        self._active_tools: list[ToolCard] = []

        self._tool_view_model: ToolViewModel = ToolViewModel(repository_manager.tools_repository)
        self._main_layout: FlowLayout

        self._setup_ui()
        self._setup_style()
        self._connect_signals()
        self._tool_view_model.load_enabled_tools()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self._create_layout()

    def _create_layout(self) -> None:
        """Create the FlowLayout and configure its margins and spacing."""
        self._main_layout = FlowLayout(min_width=self._card_width, parent=self)
        self._main_layout.setContentsMargins(Spacing.NONE, Spacing.SM, Spacing.NONE, Spacing.NONE)
        self._main_layout.setSpacing(Spacing.LG)

    @staticmethod
    def _create_description_widget(text: str) -> QLabel:
        """Create a word-wrapped, left-aligned description label.

        Args:
            text: The description text to display.

        Returns:
            A ``QLabel`` configured for multi-line display with the
            ``description`` object name set for QSS targeting.
        """
        label: QLabel = QLabel(text)
        label.setObjectName("description")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        return label

    def _setup_style(self) -> None:
        """Load and apply the QSS stylesheet for the tools grid."""
        qss: str = load_stylesheet(DashboardStyles.TOOLS_GRID)
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        """Connect ViewModel signals to their handler slots.

        Only ``tools_loaded`` is wired up; update/add/delete signals are
        stubbed out until those features are implemented.
        """
        # TODO: setup signals on changed tool,added deleted if needed
        # self._tool_view_model.tool_updated.connect(self._on_tool_updated)
        # self._tool_view_model.tool_added.connect(self._on_tool_added)
        # self._tool_view_model.tool_deleted.connect(self._on_tool_deleted)
        self._tool_view_model.tools_loaded.connect(self._load_tools)

    @Slot(list)
    def _load_tools(self, tools: list[ToolDTO]) -> None:
        """Populate the grid by creating a ToolCard for each loaded tool.

        Args:
            tools: The list of enabled tool DTOs emitted by the ViewModel.
        """
        for tool in tools:
            description_label: QLabel = self._create_description_widget(tool.description)
            tool_card: ToolCard = ToolCard(
                QIcon(tool.icon_path), QColor(Palette.CYAN_800), tool.title, description_label
            )
            tool_card.setMinimumWidth(self._card_width)
            tool_card.setFixedHeight(self._card_height)
            self._main_layout.addWidget(tool_card)

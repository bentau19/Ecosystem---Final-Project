from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QLabel, QWidget

from domain.dto.tool import ToolDTO
from views.layouts.flow_layout import FlowLayout
from app.app_state import app_state
from app.theme_manager import theme_manager
from resources.colors import Palette, Colors, LightColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
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

        self._tool_view_model = app_state.tool_viewmodel
        self._main_layout: FlowLayout

        self._setup_ui()
        self._setup_style()
        self._connect_signals()
        self._tool_view_model.load_enabled_tools()

    def _setup_ui(self) -> None:
        # Initialize the flow layout.
        self._create_layout()

    def _create_layout(self) -> None:
        # Create the FlowLayout and configure its margins and spacing.
        self._main_layout = FlowLayout(min_width=self._card_width, parent=self)
        self._main_layout.setContentsMargins(Spacing.NONE, Spacing.SM, Spacing.NONE, Spacing.NONE)
        self._main_layout.setSpacing(Spacing.LG)

    @staticmethod
    def _create_description_widget(text: str) -> QLabel:
        # Create a word-wrapped, left-aligned description label for use inside a ToolCard.
        label: QLabel = QLabel(text)
        label.setObjectName("description")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        return label

    def _setup_style(self) -> None:
        # Load and apply the themed QSS stylesheet.
        qss: str = load_stylesheet(
            DashboardStyles.TOOLS_GRID,
            themed([Colors], [LightColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        # Wire tools_loaded and theme_changed; add/update/delete signals are stubbed until needed.
        # TODO: setup signals on changed tool,added deleted if needed
        # self._tool_view_model.tool_updated.connect(self._on_tool_updated)
        # self._tool_view_model.tool_added.connect(self._on_tool_added)
        # self._tool_view_model.tool_deleted.connect(self._on_tool_deleted)
        self._tool_view_model.tools_loaded.connect(self._load_tools)
        theme_manager.theme_changed.connect(self._setup_style)

    @Slot(list)
    def _load_tools(self, tools: list[ToolDTO]) -> None:
        # Create a ToolCard for each enabled tool DTO and add it to the flow layout.
        print(tools)
        for tool in tools:
            description_label: QLabel = self._create_description_widget(tool.description)
            tool_card: ToolCard = ToolCard(
                QIcon(tool.icon_path), QColor(Palette.CYAN_800), tool.title, description_label
            )
            tool_card.setMinimumWidth(self._card_width)
            tool_card.setFixedHeight(self._card_height)
            self._main_layout.addWidget(tool_card)

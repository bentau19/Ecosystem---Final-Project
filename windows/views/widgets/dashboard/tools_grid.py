from typing import List, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QLabel, QWidget

from dto.tool import ToolDTO
from layouts.flow_layout import FlowLayout
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet
from viewmodels.tool import ToolViewModel
from views.widgets.dashboard.tool_card import ToolCard


class ToolsGrid(QWidget):
    """
    Widget that displays a grid of tools.

    Attributes:
        _card_width (int): The width of the card.
        _card_height (int): The height of the card.
    """

    def __init__(self, card_width: int = 300, card_height: int = 170, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the ToolsGrid widget.

        Args:
            card_width (int, optional): The width of the card. Defaults to 300.
            card_height (int, optional): The height of the card. Defaults to 170.
            parent (Optional[QWidget], optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)

        self._card_width: int = card_width
        self._card_height: int = card_height

        self._active_tools: List[ToolCard] = []

        self._tool_view_model: ToolViewModel = ToolViewModel()
        self._main_layout: FlowLayout

        self._setup_ui()
        self._setup_style()
        self._connect_signals()
        self._tool_view_model.load_enabled_tools()

    def _setup_ui(self) -> None:
        """
        Set up the user interface.
        """
        self._create_layout()

    def _create_layout(self) -> None:
        """
        Create the layout for the tools grid.
        """
        self._main_layout = FlowLayout(min_width=self._card_width, parent=self)
        self._main_layout.setContentsMargins(Spacing.NONE, Spacing.SM, Spacing.NONE, Spacing.NONE)
        self._main_layout.setSpacing(Spacing.LG)

    @staticmethod
    def _create_description_widget(text: str) -> QLabel:
        """
        Create a widget with a description.

        Args:
            text (str): The description text.

        Returns:
            QLabel: The created description widget.
        """
        label: QLabel = QLabel(text)
        label.setObjectName("description")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        return label

    def _setup_style(self) -> None:
        """
        Set up the style for the tools grid.
        """
        qss: str = load_stylesheet(DashboardStyles.TOOLS_GRID)
        self.setStyleSheet(qss)

    def _connect_signals(self):
        # TODO: setup signals on changed tool,added deleted if needed
        # self._tool_view_model.tool_updated.connect(self._on_tool_updated)
        # self._tool_view_model.tool_added.connect(self._on_tool_added)
        # self._tool_view_model.tool_deleted.connect(self._on_tool_deleted)
        self._tool_view_model.tools_loaded.connect(self._load_tools)

    @Slot(list)
    def _load_tools(self, tools: List[ToolDTO]) -> None:
        """
        Update the list of active tools.

        Args:
            tools (List[ToolDetail]): The list of tools.
        """
        for tool in tools:
            description_label: QLabel = self._create_description_widget(tool.description)
            tool_card: ToolCard = ToolCard(
                QIcon(tool.icon_path), QColor(tool.icon_background_color), tool.title, description_label
            )
            tool_card.setMinimumWidth(self._card_width)
            tool_card.setFixedHeight(self._card_height)
            self._main_layout.addWidget(tool_card)

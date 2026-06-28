from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QFileDialog, QLabel, QWidget

from app.app_state import app_state
from app.theme_manager import theme_manager
from domain.dto.tool import ToolDTO
from domain.tool_catalog import (
    TITLE_BACKUP,
    TITLE_CLIPBOARD,
    TITLE_SEND_FILE,
    TITLE_VIRTUAL_DRIVE,
    TITLE_WEBCAM,
)
from resources.colors import Palette, Colors, LightColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from viewmodels.file_transfer import FileTransferViewModel
from viewmodels.tool import ToolViewModel
from views.layouts.flow_layout import FlowLayout
from views.widgets.dashboard.tool_card import ToolCard

# Per-tool hint shown on the card body.  Only "Send File" is interactive; the
# feature tools are controlled by their toggle switch and are otherwise inert.
_HINT_FROM_PHONE = "Only applicable from phone"
_TOOL_HINTS: dict[str, str] = {
    TITLE_VIRTUAL_DRIVE: "Open Explorer to view",
    TITLE_CLIPBOARD: _HINT_FROM_PHONE,
    TITLE_WEBCAM: _HINT_FROM_PHONE,
    TITLE_BACKUP: _HINT_FROM_PHONE,
}


class ToolsGrid(QWidget):
    """Flow-layout grid of every tool as a :class:`~views.widgets.dashboard.tool_card.ToolCard`.

    Loads the full tool list from a :class:`~viewmodels.tool.ToolViewModel` and
    renders one card per tool, each with an enable/disable toggle.  Only the
    "Send File to Phone" card is clickable (it opens a file picker); the feature
    cards carry a hint and are turned on/off via their toggle, which writes
    through to ``tools.json`` and the matching background service.
    """

    def __init__(self, card_width: int = 300, card_height: int = 210, parent: QWidget | None = None) -> None:
        """Initialize the ToolsGrid widget.

        Args:
            card_width: Width applied to each tool card. Defaults to 300.
            card_height: Fixed height applied to each tool card. Defaults to 210.
            parent: Parent widget. Defaults to None.
        """
        super().__init__(parent)

        self._card_width: int = card_width
        self._card_height: int = card_height

        self._tool_view_model: ToolViewModel = app_state.tool_viewmodel
        self._file_transfer_viewmodel: FileTransferViewModel = app_state.file_transfer_viewmodel
        self._main_layout: FlowLayout

        self._setup_ui()
        self._setup_style()
        self._connect_signals()
        self._tool_view_model.load_tools()

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
        # Create a word-wrapped, left-aligned description label for a ToolCard.
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
        # Populate on load; restyle on theme change.
        self._tool_view_model.tools_loaded.connect(self._load_tools)
        theme_manager.theme_changed.connect(self._setup_style)

    @Slot(list)
    def _load_tools(self, tools: list[ToolDTO]) -> None:
        # Clear any previously rendered cards before repopulating (handles re-fires).
        while self._main_layout.count():
            item = self._main_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        # Render only enabled tools as display-only cards — enable/disable now
        # lives on the Settings page, not on the dashboard.
        for tool in tools:
            if not tool.is_enabled:
                continue
            self._main_layout.addWidget(self._build_card(tool))

    def _build_card(self, tool: ToolDTO) -> ToolCard:
        # Build a single display-only card; only "Send File" is clickable.
        description_label: QLabel = self._create_description_widget(tool.description)
        clickable: bool = tool.title == TITLE_SEND_FILE
        card: ToolCard = ToolCard(
            QIcon(tool.icon_path),
            QColor(Palette.CYAN_800),
            tool.title,
            description_label,
            checkable=False,
            clickable=clickable,
            hint=_TOOL_HINTS.get(tool.title, ""),
        )
        card.setMinimumWidth(self._card_width)
        card.setFixedHeight(self._card_height)

        if clickable:
            card.clicked.connect(self._on_send_file_clicked)
        return card

    @Slot()
    def _on_send_file_clicked(self) -> None:
        """Open a native file picker and send the chosen file to the connected phone."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a file to send",
            "",              # start in the OS last-used directory
            "All Files (*)",
        )
        if path:
            self._file_transfer_viewmodel.send_file(path)

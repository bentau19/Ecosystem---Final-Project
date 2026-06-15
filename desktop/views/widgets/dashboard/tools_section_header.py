from PySide6.QtCore import Slot
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout

from app.app_state import app_state
from app.theme_manager import theme_manager
from domain.dto.tool import ToolDTO
from resources.colors import DashboardColors, LightColors, LightDashboardColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from viewmodels.tool import ToolViewModel


class ToolsSectionHeader(QWidget):
    """Header row for the tools section on the dashboard.

    Displays an 'Available Tools' title on the left and a live count badge
    ('N tools available') on the right that updates whenever the tool count
    changes via the :class:`~viewmodels.tool.ToolViewModel`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the tools section header widget.

        Args:
            parent: Parent widget, defaults to None.
        """
        super().__init__(parent)

        self._title: QLabel
        self._tag: QLabel

        self._tools_view_model: ToolViewModel = app_state.tool_viewmodel

        self._setup_ui()
        self._setup_style()
        self._connect_signals()
        self._tools_view_model.load_enabled_tools()

    def _setup_ui(self) -> None:
        # Create title/tag widgets and build the horizontal layout.
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        # Create the title and tag labels.
        self._title = self._create_title()
        self._tag = self._create_tag()

    def _create_layout(self) -> None:
        # Lay out title on the left, tag on the right, with a stretch in between.
        layout: QHBoxLayout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)

        layout.addWidget(self._title)
        layout.addStretch()
        layout.addWidget(self._tag)

    @staticmethod
    def _create_title() -> QLabel:
        # Return the static 'Available Tools' heading label.
        title: QLabel = QLabel("Available Tools")
        title.setObjectName("title")
        return title

    @staticmethod
    def _create_tag() -> QLabel:
        # Start empty; _update_tag populates the real count on the first tools_changed signal.
        tag: QLabel = QLabel("")
        tag.setObjectName("tag")
        return tag

    def _setup_style(self) -> None:
        # Load and apply the themed stylesheet.
        qss: str = load_stylesheet(
            DashboardStyles.TOOLS_SECTION_HEADER,
            themed([DashboardColors], [LightDashboardColors, LightColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        # Wire tools_changed and theme_changed to their slots.
        self._tools_view_model.tools_changed.connect(self._update_tag)
        theme_manager.theme_changed.connect(self._setup_style)

    @Slot(int)
    def _update_tag(self, tools: list[ToolDTO]) -> None:
        # Update the count badge text whenever the enabled-tool count changes.
        self._tag.setText(f"{len(tools)} tools available")

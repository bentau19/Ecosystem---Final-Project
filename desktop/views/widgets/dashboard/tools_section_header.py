from PySide6.QtCore import Slot
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout

from app.app_state import app_state
from app.theme_manager import theme_manager
from resources.colors import DashboardColors, LightDashboardColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed


class ToolsSectionHeader(QWidget):
    """Header row for the tools section on the dashboard.

    Displays an 'Available Tools' title on the left and a live count badge
    ('N tools available') on the right that updates whenever the tool count
    changes via the :class:`~viewmodels.tool.ToolViewModel`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the _tools section header widget.

        Args:
            parent: Parent widget, defaults to None.
        """
        super().__init__(parent)

        self._title: QLabel
        self._tag: QLabel

        self._tools_view_model = app_state.tool_viewmodel

        self._setup_ui()
        self._setup_style()
        self._connect_signals()
        self._tools_view_model.load_enabled_tools()

    def _setup_ui(self) -> None:
        """Set up the UI for the _tools section header."""
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        """Create the child widgets for the _tools section header."""
        self._title = self._create_title()
        self._tag = self._create_tag()

    def _create_layout(self) -> None:
        """Create the layout for the _tools section header.

        Set up a QHBoxLayout with specific margins and spacing, then add
        all child widgets in the correct order with appropriate spacing.
        """
        layout: QHBoxLayout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)

        layout.addWidget(self._title)
        layout.addStretch()
        layout.addWidget(self._tag)

    @staticmethod
    def _create_title() -> QLabel:
        """Create the title label for the _tools section header.

        Returns:
            QLabel: The title label.
        """
        title: QLabel = QLabel("Available Tools")
        title.setObjectName("title")
        return title

    @staticmethod
    def _create_tag() -> QLabel:
        """Create the tag label for the _tools section header.

        Returns:
            QLabel: The tag label.
        """
        tag: QLabel = QLabel("6 tools available")
        tag.setObjectName("tag")
        return tag

    def _setup_style(self) -> None:
        """Load and apply the stylesheet for the _tools section header."""
        qss: str = load_stylesheet(
            DashboardStyles.TOOLS_SECTION_HEADER,
            themed([DashboardColors], [LightDashboardColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        """Connect ViewModel signals and theme changes to their handler slots."""
        self._tools_view_model.tool_count_changed.connect(self._update_tag)
        theme_manager.theme_changed.connect(self._setup_style)

    @Slot(int)
    def _update_tag(self, count: int) -> None:
        """Update the tag text with the tool count.

        Args:
            count (int): The count of tools.
        """
        self._tag.setText(f"{count} tools available")

from typing import Optional

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout

from resources.colors import DashboardColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet
from view_model.tool import ToolViewModel


class ToolsSectionHeader(QWidget):
    """Tools section header widget."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the _tools section header widget.

        Args:
            parent: Parent widget, defaults to None.
        """
        super().__init__(parent)

        self._title: QLabel
        self._tag: QLabel

        self._tools_view_model: ToolViewModel = ToolViewModel()

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
        """Load and apply the stylesheet for the _tools section header.

        Load the stylesheet from the resources file and apply it to the
        _tools section header widget.
        """
        qss: str = load_stylesheet(DashboardStyles.TOOLS_SECTION_HEADER, [DashboardColors])
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        """Connect the signals for the _tools section header.

        Connect the `tool_count_changed` signal of the `_tools_view_model`
        to the `_update_tag` slot.
        """
        self._tools_view_model.tool_count_changed.connect(self._update_tag)

    @Slot(int)
    def _update_tag(self, count: int) -> None:
        """Update the tag text with the tool count.

        Args:
            count (int): The count of tools.
        """
        self._tag.setText(f"{count} tools available")

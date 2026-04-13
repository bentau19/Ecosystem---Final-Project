from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QFrame, QVBoxLayout
)
from views.widgets.dashboard.phone_details_row import PhoneDetailsRow

from resources.spacing import Spacing
from views.widgets.dashboard.tools_grid import ToolsGrid
from views.widgets.dashboard.tools_section_header import ToolsSectionHeader


class DashboardContent(QScrollArea):
    """
    Main content widget for the dashboard page.

    Displays device status cards, tool cards, and navigation controls
    in a scrollable layout with proper styling and organization.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialize the MainContent widget.

        Args:
            parent: Parent widget, defaults to None
        """
        super().__init__(parent)

        self._device_status_row: PhoneDetailsRow
        self._tools_section_header: ToolsSectionHeader
        self._tools_grid: ToolsGrid

        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        Set up the main UI components and layout.
        """
        self.setObjectName("dashboardContent")
        self.viewport().setStyleSheet("background-color: #0d1117")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._create_widgets()

        self._create_layout()

    def _create_widgets(self) -> None:
        """
        Create the main content widgets.
        """
        self._device_status_row: PhoneDetailsRow = self._create_device_status_row()
        self._tools_section_header: ToolsSectionHeader = ToolsSectionHeader()
        self._tools_grid: ToolsGrid = ToolsGrid()

    def _create_layout(self) -> None:
        """
        Create the inner content widget with all dashboard components.
        """

        inner: QWidget = QWidget()

        layout: QVBoxLayout = QVBoxLayout(inner)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.NONE)

        layout.addWidget(self._device_status_row)
        layout.addSpacing(Spacing.XXL)

        layout.addWidget(self._tools_section_header)
        layout.addSpacing(Spacing.LG)

        layout.addWidget(self._tools_grid)
        layout.addStretch()

        self.setWidget(inner)

    @staticmethod
    def _create_device_status_row() -> PhoneDetailsRow:
        """
        Create the device status row.

        Returns:
            PhoneDetailsRow: The created device status row.
        """
        return PhoneDetailsRow(
        )

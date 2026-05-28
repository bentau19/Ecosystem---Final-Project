from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QFrame, QVBoxLayout
)

from app.theme_manager import theme_manager
from resources.colors import Palette, LightPalette
from resources.spacing import Spacing
from views.widgets.dashboard.phone_details_row import PhoneDetailsRow
from views.widgets.dashboard.tools_grid import ToolsGrid
from views.widgets.dashboard.tools_section_header import ToolsSectionHeader


class DashboardContent(QScrollArea):
    """Scrollable main content area for the dashboard screen.

    Displays a device-status row, a tools section header, and a flow-layout
    grid of tool cards inside a vertically scrollable, frame-less
    :class:`QScrollArea`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the DashboardContent widget.

        Args:
            parent: Parent widget, defaults to None.
        """
        super().__init__(parent)

        self._device_status_row: PhoneDetailsRow
        self._tools_section_header: ToolsSectionHeader
        self._tools_grid: ToolsGrid

        self._setup_ui()
        self._setup_style()
        self._connect_signals()

    def _setup_ui(self) -> None:
        # Configure scroll area properties, then build child widgets and layout.
        self.setObjectName("dashboardContent")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        # Instantiate the device-status row, tools section header, and tools grid.
        self._device_status_row: PhoneDetailsRow = self._create_device_status_row()
        self._tools_section_header: ToolsSectionHeader = ToolsSectionHeader()
        self._tools_grid: ToolsGrid = ToolsGrid()

    def _create_layout(self) -> None:
        # Build the inner content widget and install it as the scroll area's viewport widget.
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

    def _setup_style(self) -> None:
        # Apply the themed background to the viewport so it blends with the window.
        bg = Palette.DARK_950 if theme_manager.is_dark else LightPalette.DARK_950
        self.viewport().setStyleSheet(f"background-color: {bg};")

    def _connect_signals(self) -> None:
        # Wire theme_changed to re-apply the viewport background.
        theme_manager.theme_changed.connect(self._setup_style)

    @staticmethod
    def _create_device_status_row() -> PhoneDetailsRow:
        # Return a default-constructed PhoneDetailsRow.
        return PhoneDetailsRow()

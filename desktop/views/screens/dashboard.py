from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QApplication
)

import resources_qrc  # noqa: F401
from resources.spacing import Spacing
from utils.navigation_manager import navigation_manager, NavigationManager
from viewmodels.device import DeviceViewModel
from views.widgets.dashboard.dashboard_content import DashboardContent
from views.widgets.divider import Divider
from views.widgets.navigation.sidebar import Sidebar
from views.widgets.topbar import Topbar


class DashboardScreen(QWidget):
    """Dashboard for the PhoneLink Dashboard."""

    def __init__(self) -> None:
        """Initialize the Dashboard."""
        super().__init__()
        self._device_viewmodel: DeviceViewModel = DeviceViewModel()

        self._set_up_ui()
        self.setWindowTitle("Dashboard")

    def _set_up_ui(self) -> None:
        """Set up the UI of the Dashboard."""
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        """Create the widgets for the Dashboard."""
        self._dashboard_content = DashboardContent()
        self._sidebar = Sidebar(logo_widget_height=100)
        self._topbar = Topbar("Dashboard", "Samsung Galaxy S23 — Last synced just now", 100)

    def _setup_layout(self) -> None:
        """Set up the layout of the Dashboard."""
        # Right side: topbar + divider + content
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        right_layout.setSpacing(Spacing.NONE)
        right_layout.addWidget(self._topbar)
        right_layout.addWidget(Divider())
        right_layout.addWidget(self._dashboard_content)

        # Root: sidebar + right panel
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        root_layout.setSpacing(Spacing.NONE)
        root_layout.addWidget(self._sidebar)
        root_layout.addWidget(right_panel)


if __name__ == "__main__":
    app = QApplication([])
    window = DashboardScreen()
    window.show()
    app.exec()

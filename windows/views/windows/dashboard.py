"""
PhoneLink Dashboard - PySide6
Run: pip install PySide6
     python phonelink_dashboard.py
"""

import sys
from typing import List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout
)

from resources.spacing import Spacing
from views.widgets.dashboard.dashboard_content import DashboardContent
from views.widgets.divider import Divider
from views.widgets.navigation.sidebar import Sidebar
from views.widgets.topbar import Topbar


class DashboardWindow(QMainWindow):
    """Main window for the PhoneLink Dashboard."""

    def __init__(self) -> None:
        """Initialize the DashboardWindow."""
        super().__init__()
        self._set_up_ui()
        self.setWindowTitle("Dashboard")
        self.resize(1100, 720)

    def _set_up_ui(self) -> None:
        """Set up the UI of the DashboardWindow."""
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        """Create the widgets for the DashboardWindow."""
        self._dashboard_content = DashboardContent()
        self._sidebar = Sidebar(logo_widget_height=100)
        self._topbar = Topbar("Dashboard", "Samsung Galaxy S23 — Last synced just now", 100)

    def _setup_layout(self) -> None:
        """Set up the layout of the DashboardWindow."""
        central_widget_content = self._create_central_widget_content()
        central_widget = self._create_central_widget(central_widget_content)
        self.setCentralWidget(central_widget)

    def _create_central_widget_content(self) -> QWidget:
        """Create the central widget content (dashboard content + topbar)."""
        central_widget_content = QWidget()
        central_widget_content_layout = QVBoxLayout(central_widget_content)
        central_widget_content_layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        central_widget_content_layout.setSpacing(Spacing.NONE)
        central_widget_content_layout.addWidget(self._topbar)
        central_widget_content_layout.addWidget(Divider())
        central_widget_content_layout.addWidget(self._dashboard_content)
        return central_widget_content

    def _create_central_widget(self, central_widget_content: QWidget) -> QWidget:
        """Create the central widget."""
        central_widget = QWidget()
        central_widget_layout = QHBoxLayout(central_widget)
        central_widget_layout.setSpacing(Spacing.NONE)
        central_widget_layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        central_widget_layout.addWidget(self._sidebar)
        central_widget_layout.addWidget(central_widget_content)
        return central_widget


def main(args: List[str]) -> None:
    """Run the DashboardWindow application."""
    app = QApplication(args)
    window = DashboardWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main(sys.argv)

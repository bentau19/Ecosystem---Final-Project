"""
PhoneLink Dashboard - PySide6
Run: pip install PySide6
     python phonelink_dashboard.py
"""

import sys
from PySide6.QtGui import QFont, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout
)

from resources.colors import Colors
from views.main_page import MainContent
from widgets.navigation.sidebar import Sidebar


class DashboardWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Syncdose")
        self.resize(1100, 720)
        self.setMinimumSize(900, 600)

        # Dark palette for native widgets
        # palette = QPalette()
        # # palette.setColor(QPalette.ColorRole.Window, QColor(Colors.BACKGROUND))
        # # palette.setColor(QPalette.ColorRole.WindowText, QColor(Colors.TEXT))
        # # palette.setColor(QPalette.ColorRole.Base, QColor(Colors.SIDEBAR_BACKGROUND))
        # # palette.setColor(QPalette.ColorRole.Text, QColor(Colors.TEXT))
        # self.setPalette(palette)

        central = QWidget()
        central.setStyleSheet(f"background: {Colors.BACKGROUND};")
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(Sidebar())
        layout.addWidget(MainContent())


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DashboardWindow()
    window.show()
    sys.exit(app.exec())

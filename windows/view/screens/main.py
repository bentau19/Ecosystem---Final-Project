import sys

from PySide6.QtWidgets import QApplication, QWidget, QScrollArea, QVBoxLayout, QHBoxLayout

from view.widgets.all_tools_cards import AllToolsCards
from view.widgets.phone_card import PhoneCardWidget
from windows.view.layouts.grid_flow_layout import GridFlowLayout


class MainScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.features = [
            "settings",
            "Backup",
        ]
        self.t = AllToolsCards()

        self.configure_ui()
        self._load_style()

    def configure_ui(self) -> None:
        layout = QHBoxLayout()
        self.setLayout(layout)

        phone_details_card: PhoneCardWidget = PhoneCardWidget("samsung t", "android", 35, True)
        layout.addWidget(phone_details_card)

        layout.addWidget(self.t)

    def _load_style(self) -> None:
        """Load and apply the external QSS stylesheet from ``../qss/main.qss``.

        :raises FileNotFoundError: If the QSS file does not exist at the expected path.
        """
        with open("../qss/main.qss", "r") as f:
            self.setStyleSheet(f.read())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("""
    * {
        border: 1px solid rgba(255, 0, 0, 120);
    }
    """)
    window = MainScreen()
    window.showMaximized()
    sys.exit(app.exec())

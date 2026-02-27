import sys

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QHBoxLayout

from view.widgets.phone_card import PhoneCardWidget
from windows.view.layouts.flow_layout import FlowLayout


class MainScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.features = [
            "settings",
            "Backup",
        ]
        self.configure_ui()
        self._load_style()

    def configure_ui(self) -> None:
        layout = FlowLayout()
        self.setLayout(layout)
        phone_details_card: PhoneCardWidget = PhoneCardWidget("samsung t", "android", 35, True)
        layout.addWidget(phone_details_card)
        phone_details_card: PhoneCardWidget = PhoneCardWidget("samsung t", "android", 35, True)
        layout.addWidget(phone_details_card)

    def _load_style(self) -> None:
        """Load and apply the external QSS stylesheet from ``../qss/main.qss``.

        :raises FileNotFoundError: If the QSS file does not exist at the expected path.
        """
        with open("../qss/main.qss", "r") as f:
            self.setStyleSheet(f.read())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    print(QFontDatabase.families())
    window = MainScreen()
    window.showMaximized()
    sys.exit(app.exec())

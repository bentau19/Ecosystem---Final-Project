import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QApplication, QLabel, QGridLayout, QSizePolicy
import qtawesome as qta


class ToolCard(QFrame):
    def __init__(self, icon: QIcon, title: str, description: str):
        super().__init__()
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        self.icon = icon
        self.title = title
        self.description = description
        self._init_ui()
        self._load_style()

    def _init_ui(self):
        layout = QGridLayout()
        self.setLayout(layout)
        icon: QLabel = QLabel()
        icon.setPixmap(self.icon.pixmap(30, 30))
        icon.setObjectName("icon")

        layout.addWidget(icon, 0, 0, 1, 1)
        label_title: QLabel = QLabel(self.title)
        label_title.setObjectName("title")
        layout.addWidget(label_title, 1, 0, 1, 1)
        label_description: QLabel = QLabel(self.description)
        label_description.setObjectName("description")
        layout.addWidget(label_description, 2, 0, 1, 1)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

    def _load_style(self) -> None:
        """Load and apply the external QSS stylesheet from ``../qss/phone_card.qss``.

        :raises FileNotFoundError: If the QSS file does not exist at the expected path.
        """
        with open("../qss/tool_card.qss", "r") as f:
            self.setStyleSheet(f.read())

# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     win.show()
#     sys.exit(app.exec())

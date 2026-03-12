from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from resources.colors import Colors


class StatCard(QWidget):
    def __init__(self, icon: str, label: str, value: str, sub: str = "", parent=None):
        """
        Initialize a StatCard widget.

        Args:
            icon (str): The icon to display on the card.
            label (str): The label text to display on the card.
            value (str): The value text to display on the card.
            sub (str, optional): The sub label text to display on the card. Defaults to "".
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self._icon = icon
        self._label = label
        self._value = value
        self._sub = sub

        self._setup_ui()

    def _create_widgets(self) -> None:
        """
        Create all child widgets for the stat card.
        """

        self._icon_label = self._create_icon_label()
        self._title_label = self._create_title_label()
        self._value_label = self._create_value_label()
        self._secondary_value_label = self._create_secondary_value_label()

    def _create_icon_label(self) -> QLabel:
        """
        Create the stat card icon label.
        """
        icon_label = QLabel(self._icon)
        icon_label.setFixedSize(30, 30)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(
            f"background: rgba(0,229,255,0.08); border-radius: 8px; font-size: 14px;"
        )
        return icon_label

    def _create_title_label(self) -> QLabel:
        """
        Create the stat card title label.
        """
        title_label = QLabel(self._label.upper())
        title_label.setStyleSheet(f"color: {Colors.TEXT}; font-size: 12px;")
        return title_label

    def _create_value_label(self) -> QLabel:
        """
        Create the stat card value label.
        """
        value_label = QLabel(self._value)
        value_label.setStyleSheet(f"color: {Colors.TEXT}; font-size: 20px; font-weight: 600;")
        return value_label

    def _create_secondary_value_label(self) -> QLabel:
        """
        Create the stat card sub label.
        """
        secondary_value_label = QLabel(self._sub)
        secondary_value_label.setStyleSheet(f"color: {Colors.MUTED}; font-size: 12px;")
        return secondary_value_label

    def _create_layout(self):
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)

        layout.setSpacing(4)

        layout.addWidget(self._icon_label)

        layout.addSpacing(6)

        layout.addWidget(self._title_label)

        layout.addWidget(self._value_label)
        layout.addSpacing(4)

        layout.addWidget(self._secondary_value_label)

        layout.addStretch()

    def _setup_style_sheet(self) -> None:
        """
        Set up the stylesheet for the stat card.
        """
        self.setStyleSheet(f"""
            StatCard {{
                background: {Colors.SIDEBAR_BACKGROUND};
                border: 1px solid {Colors.BORDER};
                border-radius: 14px;
            }}
            StatCard:hover {{
                border: 1px solid #2a2d38;
            }}
        """)

    def _setup_ui(self):
        self._create_widgets()
        self._create_layout()

        self.setObjectName("batteryCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._setup_style_sheet()
        # self._load_style()

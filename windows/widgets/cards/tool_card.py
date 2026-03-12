from pathlib import Path

from PySide6.QtCore import Qt, QFile, QTextStream
from PySide6.QtWidgets import QWidget, QSizePolicy, QVBoxLayout, QLabel
from resources.colors import Colors


class ToolCard(QWidget):
    def __init__(self, icon, name, description, accent, icon_background, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.name = name
        self.description = description
        self.accent = accent
        self.icon_background = icon_background

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._init_ui()
        self.load_style()

    def _init_ui(self) -> None:
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(160)
        self.setObjectName("toolCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(6)

        layout.addWidget(self._init_icon_label())
        layout.addSpacing(4)

        layout.addWidget(self._init_name_label())

        layout.addWidget(self._init_description_label())
        layout.addStretch()

    def _init_icon_label(self) -> QLabel:
        icon_label = QLabel(self.icon)
        icon_label.setFixedSize(44, 44)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(f"background: {self.icon_background}; border-radius: 12px; font-size: 20px;")
        return icon_label

    def _init_name_label(self) -> QLabel:
        name_label = QLabel(self.name)
        name_label.setStyleSheet(f"color: {Colors.TEXT}; font-size: 14px; font-weight: 700; background: transparent;")
        return name_label

    def _init_description_label(self) -> QLabel:
        desc_label = QLabel(self.description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color: {Colors.MUTED}; font-size: 12px; line-height: 1.5; background: transparent;")
        return desc_label

    def load_style(self) -> None:
        qss_file: QFile = QFile(":/styles/tool_card.qss")

        if not qss_file.open(QFile.OpenModeFlag.ReadOnly):
            return

        stream = QTextStream(qss_file)
        qss = stream.readAll()

        qss = qss.replace("{{SURFACE}}", Colors.SIDEBAR_BACKGROUND)
        qss = qss.replace("{{SURFACE2}}", Colors.SURFACE2)
        qss = qss.replace("{{BORDER}}", Colors.BORDER)

        self.setStyleSheet(qss)

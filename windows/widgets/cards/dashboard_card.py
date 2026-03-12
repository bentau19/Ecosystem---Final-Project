from PySide6.QtCore import Signal, QEvent
from PySide6.QtGui import QPixmap, Qt, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QWidget


class DashboardCard(QWidget):
    clicked = Signal()

    def __init__(self, icon: QPixmap, title: str, content: QWidget, parent=None):
        super().__init__(parent)

        self._icon = icon
        self._title = title
        self._content = content

        self._setup_ui()

    def _setup_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._create_widgets()
        self._create_layout()
        self._apply_style()

    def _create_widgets(self):
        pass

    def _create_layout(self):
        pass

    def _apply_style(self):
        pass

    def mouseReleaseEvent(self, event: QMouseEvent):
        """
        Handles mouse release events.

        Emits a clicked signal when the left mouse button is released.

        Args:
            event (QMouseEvent): The mouse event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

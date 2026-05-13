from PySide6.QtGui import QPainter, Qt, QBrush, QColor, QLinearGradient, QPaintEvent
from PySide6.QtWidgets import QWidget

from resources.colors import Colors


class Bar(QWidget):
    """A custom widget that displays a horizontal battery level indicator.
    
    This widget renders a battery bar with a background track and a gradient fill
    that represents the current battery percentage. The bar has a fixed height
    and uses a green gradient for the fill.
    
    Args:
        percent (int): Battery percentage (0-100)
        parent (Optional[QWidget]): Parent widget, defaults to None
    """

    def __init__(self, percent: int, gradient_start: QColor, gradient_end: QColor,
                 parent: QWidget | None = None) -> None:
        """Initialize the BatteryBar widget.
        
        Args:
            percent (int): Battery percentage (0-100)
            parent (Optional[QWidget]): Parent widget, defaults to None
        """
        super().__init__(parent)
        self._percentage = percent

        self._gradient_start = gradient_start
        self._gradient_end = gradient_end
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setFixedHeight(7)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Handle the paint event to draw the battery bar.
        
        This method is called automatically when the widget needs to be redrawn.
        It creates a painter with antialiasing and draws the background track
        and battery fill.
        
        Args:
            event (QPaintEvent): The paint event
        """
        painter: QPainter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width: int = self.width()
        height: int = self.height()

        self._draw_background_track(painter, width, height)
        self._draw_battery_fill(painter, width, height)

    @staticmethod
    def _draw_background_track(painter: QPainter, width: int, height: int) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(Colors.SURFACE_SECONDARY)))
        painter.drawRoundedRect(0, 0, width, height, 3, 3)

    def _draw_battery_fill(self, painter: QPainter, width: int, height: int) -> None:
        fill_width: int = int(width * self._percentage / 100)
        gradient: QLinearGradient = QLinearGradient(0, 0, fill_width, 0)
        gradient.setColorAt(0, self._gradient_start)
        gradient.setColorAt(1, self._gradient_end)
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(0, 0, fill_width, height, 3, 3)

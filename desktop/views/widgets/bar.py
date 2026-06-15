from PySide6.QtGui import QPainter, Qt, QBrush, QColor, QLinearGradient, QPaintEvent
from PySide6.QtWidgets import QWidget

from resources.colors import Colors


class Bar(QWidget):
    """A custom widget that displays a horizontal level indicator bar.

    Renders a rounded background track and a rounded gradient fill scaled to
    the current percentage. The fill colors are configurable via
    *gradient_start* and *gradient_end*, so this widget can represent battery
    level, storage usage, or any other percentage-based metric.
    """

    def __init__(self, percent: int, gradient_start: QColor, gradient_end: QColor,
                 parent: QWidget | None = None) -> None:
        """Initialize the Bar widget.

        Args:
            percent: Fill percentage, clamped to ``[0, 100]``.
            gradient_start: Color at the start (left edge) of the fill gradient.
            gradient_end: Color at the end (right edge) of the fill gradient.
            parent: Optional parent widget, defaults to ``None``.
        """
        super().__init__(parent)
        self._percentage: int = percent

        self._gradient_start: QColor = gradient_start
        self._gradient_end: QColor = gradient_end
        self._setup_ui()

    def _setup_ui(self) -> None:
        # Fix the bar height to 7 px so it renders as a thin horizontal track.
        self.setFixedHeight(7)

    @property
    def percent(self) -> int:
        """Current fill level in the range ``[0, 100]``."""
        return self._percentage

    def set_percent(self, percent: int) -> None:
        """Update the fill percentage and schedule a repaint.

        Args:
            percent: New fill level clamped to ``[0, 100]``.
        """
        self._percentage = max(0, min(100, percent))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Handle the paint event to draw the bar.

        Called automatically by Qt when the widget needs to be redrawn. Creates
        a painter with antialiasing and draws the background track and fill.

        Args:
            event: The paint event delivered by Qt.
        """
        painter: QPainter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width: int = self.width()
        height: int = self.height()

        self._draw_background_track(painter, width, height)
        self._draw_battery_fill(painter, width, height)

    @staticmethod
    def _draw_background_track(painter: QPainter, width: int, height: int) -> None:
        # Draw the full-width muted background track behind the fill.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(Colors.SURFACE_SECONDARY)))
        painter.drawRoundedRect(0, 0, width, height, 3, 3)

    def _draw_battery_fill(self, painter: QPainter, width: int, height: int) -> None:
        # Draw the gradient fill scaled to the current percentage.
        fill_width: int = int(width * self._percentage / 100)
        gradient: QLinearGradient = QLinearGradient(0, 0, fill_width, 0)
        gradient.setColorAt(0, self._gradient_start)
        gradient.setColorAt(1, self._gradient_end)
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(0, 0, fill_width, height, 3, 3)

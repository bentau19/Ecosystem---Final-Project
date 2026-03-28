from typing import Optional

from PySide6.QtCore import Qt, QPoint, Property, QPropertyAnimation
from PySide6.QtGui import (
    QColor,
    QPainter,
    QBrush, QPaintEvent,
)
from PySide6.QtWidgets import QWidget

from resources.colors import Colors


class PulsingDot(QWidget):
    """An animated green pulsing dot widget for visual indicators.

      This widget displays a green dot with a pulsing ring animation that expands
      outward and fades. It's commonly used to indicate active status, connectivity,
      or ongoing processes. The animation runs continuously with a 60-frame cycle.
      """

    opacity = Property(float, lambda self: self._get_opacity(), lambda self, v: self._set_opacity(v))

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the pulsing dot widget.

        Args:
            parent (Optional[QWidget]): Parent widget, defaults to None.
        """

        super().__init__(parent)

        self._opacity: float = 1.0
        self.anim: QPropertyAnimation

        self._setup_ui()

    def _setup_ui(self):
        """Sets up the widget with fixed size (30x30), initializes animation properties, and starts the animation timer."""

        self.setFixedSize(30, 30)

        self.anim: QPropertyAnimation = QPropertyAnimation(self, b"opacity")

        self.anim.setDuration(1200)
        self.anim.setKeyValueAt(0.0, 1.0)
        self.anim.setKeyValueAt(0.5, 0.2)
        self.anim.setKeyValueAt(1.0, 1.0)
        self.anim.setLoopCount(-1)
        self.anim.start()

    def _get_opacity(self) -> float:
        """Getter for the opacity property."""
        return self._opacity

    def _set_opacity(self, value: float) -> None:
        """Setter for the opacity property.

        Updates the opacity value and repaints the widget.

        Args:
            value (float): The new opacity value.
        """
        self._opacity = value
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Handle the paint event to draw the pulsing dot.

        Args:
            event: The paint event object.
        """
        painter: QPainter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)
        painter.setPen(Qt.PenStyle.NoPen)

        # Center coordinates and base radius
        cx: int = 15
        cy: int = 15
        radius: int = 6

        # Draw the pulsing rings
        for i in range(2):
            glow_size: int = radius + (i * 3)  # Each ring gets bigger
            alpha: int = 60 - (i * 15)  # Each ring gets more transparent
            color: QColor = QColor(Colors.GREEN)
            color.setAlpha(alpha)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPoint(cx, cy), glow_size, glow_size)

        # Draw the central dot
        painter.setBrush(QBrush(QColor(Colors.GREEN)))
        painter.drawEllipse(QPoint(cx, cy), radius, radius)

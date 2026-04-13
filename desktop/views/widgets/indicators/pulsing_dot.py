from PySide6.QtCore import Qt, QPoint, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QColor,
    QPainter,
    QBrush, QPaintEvent,
)
from PySide6.QtWidgets import QWidget

from resources.colors import Colors


class PulsingDot(QWidget):
    """An animated green pulsing dot widget for visual indicators.

    Displays a green dot with a pulsing ring animation that expands
    outward and fades. Commonly used to indicate active status, connectivity,
    or ongoing processes. The animation runs continuously with a 2-second cycle.
    """

    opacity = Property(float, lambda self: self._get_opacity(), lambda self, v: self._set_opacity(v))

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the pulsing dot widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._opacity: float = 1.0
        self.anim: QPropertyAnimation

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set fixed size and start the looping opacity animation."""
        self.setFixedSize(30, 30)

        self.anim: QPropertyAnimation = QPropertyAnimation(self, b"opacity")

        self.anim.setDuration(2000)
        self.anim.setKeyValueAt(0.0, 1.0)
        self.anim.setKeyValueAt(0.5, 0.45)
        self.anim.setKeyValueAt(1.0, 1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.anim.setLoopCount(-1)  # -1 loops indefinitely
        self.anim.start()

    def _get_opacity(self) -> float:
        """Return the current opacity value used by the animation property.

        Returns:
            The current opacity as a float in [0.0, 1.0].
        """
        return self._opacity

    def _set_opacity(self, value: float) -> None:
        """Set the opacity value and schedule a repaint.

        Args:
            value: New opacity value in [0.0, 1.0].
        """
        self._opacity = value
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the pulsing dot and its glow ring.

        Args:
            event: The paint event.
        """
        painter: QPainter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)
        painter.setPen(Qt.PenStyle.NoPen)

        # Center coordinates and base radius
        cx: int = 15
        cy: int = 15
        radius: int = 6

        # Draw the pulsing rings (one soft glow ring around the core)
        for i in range(1):
            glow_size: int = radius + (i + 1) * 4  # ring at +4 px from core
            alpha: int = 55 - (i * 30)             # 55: soft fade
            color: QColor = QColor(Colors.GREEN)
            color.setAlpha(alpha)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPoint(cx, cy), glow_size, glow_size)

        # Draw the central dot
        painter.setBrush(QBrush(QColor(Colors.GREEN)))
        painter.drawEllipse(QPoint(cx, cy), radius, radius)

"""Rounded-square device icon with a smartphone SVG overlay."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QWidget

from resources.paths import Icons


class DeviceIcon(QLabel):
    """
    40×40 rounded-square icon widget.

    Renders a semi-transparent colored background and a smartphone SVG
    in the center.
    """

    _SIZE: int = 48
    _RADIUS: int = 12
    _ICON_MARGIN: int = 9

    def __init__(self, icon_color: str, parent: QWidget | None = None) -> None:
        """
        Args:
            icon_color: Hex color for the icon background tint.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._icon_color = icon_color
        self.setFixedSize(self._SIZE, self._SIZE)
        self._render_icon()

    def _render_icon(self) -> None:
        """Paint the icon to a pixmap and bind it to this label."""
        pixmap = QPixmap(self._SIZE, self._SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rounded-square tinted background
        bg = QColor(self._icon_color)
        bg.setAlpha(200)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self._SIZE, self._SIZE, self._RADIUS, self._RADIUS)
        painter.fillPath(path, bg)

        # Smartphone SVG overlay
        renderer = QSvgRenderer(Icons.SMARTPHONE)
        m = self._ICON_MARGIN
        renderer.render(painter, QRectF(m, m, self._SIZE - m * 2, self._SIZE - m * 2))

        painter.end()
        self.setPixmap(pixmap)

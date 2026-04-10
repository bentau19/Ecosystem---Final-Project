import json
import socket
import time
from enum import StrEnum

import qrcode
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class DataKey(StrEnum):
    """Keys used in the JSON payload encoded into the QR code."""

    IP = "ip"


# ── Corner bracket constants ───────────────────────────────────────────────────
_BRACKET_COLOR = QColor(0, 212, 170)  # teal accent
_BRACKET_LENGTH = 24  # px — arm length of each L
_BRACKET_WIDTH = 4  # px — stroke thickness
_BRACKET_RADIUS = 6  # px — inner corner rounding
_BRACKET_INSET = 12  # px — distance from widget edge

_QR_CORNER_RADIUS = 24  # px — must match QSS border-radius on #QR


class QR(QLabel):
    """
    QR code widget with teal corner-bracket decorations and clipped rounded corners.

    Uses error correction level H (30 % recovery capacity).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._pixmap: QPixmap
        self._pixmap_scaled: QPixmap

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._load_qr()
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set the generated QR Pixmap on the label."""
        self.setPixmap(self._pixmap)

    def refresh_qr(self) -> None:
        """Regenerate and display a new QR code."""
        self._load_qr()
        self.setPixmap(self._pixmap)

    def _load_qr(self) -> None:
        """Generate the QR code encoding the device's local IP address."""
        hostname = socket.gethostname()
        ip: str = socket.gethostbyname(hostname)

        ip_hash = hash(time.time()) + hash(ip)
        data: dict[str, int] = {DataKey.IP.value: ip_hash}

        qr = qrcode.QRCode(
            box_size=10,
            border=2,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
        )
        qr.add_data(json.dumps(data))
        qr.make(fit=True)

        qr_image: ImageQt = ImageQt(
            qr.make_image(fill_color="black", back_color="white").get_image()
        )

        self._pixmap = QPixmap.fromImage(qr_image)
        # Seed the scaled copy immediately so paintEvent has something to draw
        # before the first resizeEvent fires.
        self._pixmap_scaled = self._pixmap

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the QR Pixmap clipped to rounded corners, then overlay corner brackets.

        Args:
            event: The paint event.
        """
        # Always rescale to current size right before drawing — avoids stale cache
        # from rapid resize events being coalesced into fewer paint calls.
        self._update_scaled_pixmap()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── Clip to rounded rect so the QR image corners are properly rounded ─
        clip_path = QPainterPath()
        clip_path.addRoundedRect(
            QRectF(self.rect()),
            _QR_CORNER_RADIUS,
            _QR_CORNER_RADIUS,
        )

        painter.setClipPath(clip_path)

        pixmap = self._pixmap
        if pixmap and not pixmap.isNull():
            scaled = self._pixmap_scaled
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        # ── Release clip — brackets are drawn on top of the rounded frame ─────
        painter.setClipping(False)
        self._draw_corner_brackets(painter)

        painter.end()

    def _draw_corner_brackets(self, painter: QPainter) -> None:
        """
        Draw teal L-shaped brackets at all four corners of the widget.

        Args:
            painter: Active QPainter for this widget.
        """
        pen = QPen(
            _BRACKET_COLOR,
            _BRACKET_WIDTH,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        w, h = self.width(), self.height()
        i = _BRACKET_INSET
        L = _BRACKET_LENGTH
        r = _BRACKET_RADIUS

        corners = [
            (i, i, +1, +1),  # top-left
            (w - i, i, -1, +1),  # top-right
            (i, h - i, +1, -1),  # bottom-left
            (w - i, h - i, -1, -1),  # bottom-right
        ]

        for cx, cy, hd, vd in corners:
            path = QPainterPath()
            path.moveTo(cx + hd * L, cy)
            path.lineTo(cx + hd * r, cy)
            path.quadTo(cx, cy, cx, cy + vd * r)
            path.lineTo(cx, cy + vd * L)
            painter.drawPath(path)

    def _update_scaled_pixmap(self) -> None:
        """Rescale the cached Pixmap to fit the current widget size.

        Uses the smaller of width/height to keep the QR square. Skips
        the rescale if the Pixmap is null or the widget has no area yet.
        """
        if self._pixmap.isNull():
            return

        size = min(self.width(), self.height())
        if size <= 0:
            return

        self._pixmap_scaled = self._pixmap.scaled(
            self.width(),
            self.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,  # crisp at every size
        )

    def resizeEvent(self, event: QResizeEvent, /) -> None:
        """Request a repaint whenever the widget is resized.

        Args:
            event: The resize event carrying old and new sizes.
        """
        event.accept()
        min_size = min(self.width(), self.height())
        self.resize(min_size, min_size)

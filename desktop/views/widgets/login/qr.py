import json
from enum import StrEnum

import qrcode
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import QLabel, QWidget, QSizePolicy

from resources.colors import Palette
from resources.spacing import Spacing
from utils import network


class DataKey(StrEnum):
    """Keys used in the JSON payload encoded into the QR code."""

    IP = "ip"


# ── Corner bracket constants ───────────────────────────────────────────────────
_BRACKET_COLOR: QColor = QColor(Palette.TEAL_400)  # teal accent
_BRACKET_LENGTH: int = 24  # px — arm length of each L
_BRACKET_WIDTH: int = 4  # px — stroke thickness
_BRACKET_RADIUS: int = 6  # px — inner corner rounding
_BRACKET_INSET: int = 12  # px — distance from widget edge

# Must stay in sync with the border-radius on #QR in left-panel.qss
_QR_CORNER_RADIUS: int = Spacing.XXL


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

        self._load_qr()
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setPixmap(self._pixmap)

    def refresh_qr(self) -> None:
        """Regenerate and display a new QR code."""
        self._load_qr()
        self.setPixmap(self._pixmap)

    def _load_qr(self) -> None:
        ip: str = network.get_ip()

        data: dict[str, str] = {DataKey.IP.value: ip}

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
        l = _BRACKET_LENGTH
        r = _BRACKET_RADIUS

        corners = [
            (i, i, +1, +1),  # top-left
            (w - i, i, -1, +1),  # top-right
            (i, h - i, +1, -1),  # bottom-left
            (w - i, h - i, -1, -1),  # bottom-right
        ]

        for cx, cy, hd, vd in corners:
            path = QPainterPath()
            path.moveTo(cx + hd * l, cy)
            path.lineTo(cx + hd * r, cy)
            path.quadTo(cx, cy, cx, cy + vd * r)
            path.lineTo(cx, cy + vd * l)
            painter.drawPath(path)

    def _update_scaled_pixmap(self) -> None:
        # Uses the smaller dimension to keep the QR square; no-ops if null or zero-size.
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
        super().resizeEvent(event)

        min_size = min(self.width(), self.height())
        if self.width() != self.height():
            self.resize(min_size, min_size)

        self.resize(min_size, min_size)

        frame = self.frameGeometry()
        center = self.screen().availableGeometry().center()
        frame.moveCenter(center)
        # self.move(frame.topLeft())

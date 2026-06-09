"""Animated circular arc loading spinner widget."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPaintEvent
from PySide6.QtWidgets import QWidget

from app.theme_manager import theme_manager
from resources.colors import Colors, Palette, LightPalette


class LoadingSpinner(QWidget):
    """Animated circular arc spinner widget.

    Draws a muted full-circle track with a 100-degree cyan arc that rotates
    clockwise continuously.  The timer runs only while the widget is visible —
    it auto-starts in :meth:`showEvent` and auto-stops in :meth:`hideEvent`
    (zero CPU cost when hidden).

    Args:
        size:   Diameter of the spinner in pixels.  Defaults to 40.
        parent: Optional parent widget.
    """

    # Degrees advanced per timer tick (~60 fps × 6° ≈ one full rotation per second)
    _STEP: int = 6
    # Sweep length of the foreground arc in degrees
    _ARC_SPAN: int = 100
    # Pen width in pixels for both track and foreground arc
    _PEN_WIDTH: int = 3

    def __init__(self, size: int = 40, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle: int = 0
        self._size: int = size
        self._track_color: QColor = QColor()

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        # Fix widget to a square and create the rotation timer (not yet started).
        self.setFixedSize(self._size, self._size)

        self._timer: QTimer = QTimer(self)
        self._timer.setInterval(16)  # ~60 fps
        self._timer.timeout.connect(self._tick)

    def _apply_style(self) -> None:
        # Resolve theme-dependent track color; arc color stays cyan in both themes.
        self._track_color = QColor(
            Palette.DARK_750 if theme_manager.is_dark else LightPalette.DARK_750
        )
        self.update()

    def _connect_signals(self) -> None:
        # Re-resolve the track color whenever the system theme switches.
        theme_manager.theme_changed.connect(self._apply_style)

    # ── Timer lifecycle ────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:  # noqa: ANN001
        """Start the rotation timer when the widget becomes visible."""
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: ANN001
        """Stop the rotation timer when the widget is hidden."""
        self._timer.stop()
        super().hideEvent(event)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _tick(self) -> None:
        # Advance the rotation angle and schedule a repaint.
        self._angle = (self._angle + self._STEP) % 360
        self.update()

    # ── Paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the muted track ring and the rotating cyan arc.

        Args:
            event: The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Inset rect so the pen stroke doesn't clip at the widget edges.
        margin = self._PEN_WIDTH
        rect = self.rect().adjusted(margin, margin, -margin, -margin)

        # ── Muted full-circle track ────────────────────────────────────────────
        track_pen = QPen(self._track_color, self._PEN_WIDTH)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(rect, 0, 360 * 16)  # full circle, 1/16° units

        # ── Rotating cyan foreground arc ───────────────────────────────────────
        # Qt angle conventions: 0° = 3 o'clock, positive = CCW.
        # We anchor the arc start at 12 o'clock (90°) and rotate CW (negative span).
        arc_pen = QPen(QColor(Colors.ACCENT_PRIMARY), self._PEN_WIDTH)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        start_angle = (90 - self._angle) * 16
        span_angle = -self._ARC_SPAN * 16  # negative = clockwise
        painter.drawArc(rect, start_angle, span_angle)

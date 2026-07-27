from PySide6.QtCore import Qt, Slot, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QAbstractButton, QWidget

from app.theme_manager import theme_manager
from resources.colors import Colors, LightColors


# Colors used by paintEvent — resolved once here to avoid per-frame string lookups.
_ON_COLOR   = QColor(Colors.ACCENT_PRIMARY)   # Cyan-400 — same in both themes
_OFF_DARK   = QColor(Colors.BORDER_DEFAULT)   # Dark-mode "off" pill
_OFF_LIGHT  = QColor(LightColors.BORDER_DEFAULT)  # Light-mode "off" pill
_KNOB_COLOR = QColor("#FFFFFF")


class ToggleSwitch(QAbstractButton):
    """Animated pill-shaped toggle switch.

    Renders a rounded pill background that slides between a muted neutral
    (off) and the primary accent colour (on), with a white circular knob
    that animates between the two sides.

    Usage::

        toggle = ToggleSwitch(checked=True)
        toggle.toggled.connect(my_slot)
    """

    # Visual dimensions
    _WIDTH:  int = 52
    _HEIGHT: int = 28
    _PADDING: int = 2   # gap between knob edge and pill edge

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        """Create a toggle switch.

        Args:
            checked: Initial checked (on) state. Defaults to ``False``.
            parent:  Optional parent widget.
        """
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(self._WIDTH, self._HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # _knob_pos: 0.0 = knob fully left (off) · 1.0 = knob fully right (on)
        self._knob_pos: float = 1.0 if checked else 0.0

        self._anim: QVariantAnimation = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)

        # Repaint when the theme changes so off-state color updates.
        theme_manager.theme_changed.connect(self.update)
        self.toggled.connect(self._on_toggled)

    # ── Animation ─────────────────────────────────────────────────────────────

    @Slot(bool)
    def _on_toggled(self, checked: bool) -> None:
        # Animate from current position to the target (0.0 or 1.0).
        self._anim.stop()
        self._anim.setStartValue(self._knob_pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def set_checked_silent(self, checked: bool) -> None:
        """Reflect an externally-driven state change without emitting ``toggled``.

        Used when the state is changed programmatically (e.g. the phone pushes a
        new setting) so the write-back into the ViewModel is not re-triggered.

        ``setChecked`` alone won't move the knob: the knob position is
        animation-driven off the ``toggled`` signal, which we must suppress here
        to avoid the write-back.  So we set the state with signals blocked, then
        drive the animation directly.

        Args:
            checked: New checked (on) state.
        """
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)
        # toggled was suppressed, so animate the knob to the new side ourselves.
        self._on_toggled(checked)

    @Slot(object)
    def _on_anim_value(self, value: object) -> None:
        # QVariantAnimation emits QVariant which unboxes to float.
        self._knob_pos = float(value)  # type: ignore[arg-type]
        self.update()

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Draw the pill background and animated knob."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        radius = h // 2

        # ── Background pill ──────────────────────────────────────────────────
        # Lerp between off colour and on colour based on knob position so the
        # background colour animates smoothly alongside the knob.
        off_color = _OFF_DARK if theme_manager.is_dark else _OFF_LIGHT
        t = self._knob_pos
        r = int(off_color.red()   + t * (_ON_COLOR.red()   - off_color.red()))
        g = int(off_color.green() + t * (_ON_COLOR.green() - off_color.green()))
        b = int(off_color.blue()  + t * (_ON_COLOR.blue()  - off_color.blue()))
        bg = QColor(r, g, b)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(0, 0, w, h, radius, radius)

        # ── Knob circle ──────────────────────────────────────────────────────
        knob_size = h - self._PADDING * 2
        max_travel = w - knob_size - self._PADDING * 2
        knob_x = int(self._PADDING + self._knob_pos * max_travel)

        p.setBrush(_KNOB_COLOR)
        p.drawEllipse(knob_x, self._PADDING, knob_size, knob_size)

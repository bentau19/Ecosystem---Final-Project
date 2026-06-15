from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.theme_manager import theme_manager
from resources.colors import LightLoadingOverlayColors, LightPalette, LoadingOverlayColors, Palette
from resources.paths import LoadingStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from views.widgets.loading.spinner import LoadingSpinner

# Background fill opacity (0–255) for the semi-transparent surface layer.
_DARK_BG_ALPHA: int = 210   # ~82 % opaque on dark backgrounds
_LIGHT_BG_ALPHA: int = 220  # ~86 % opaque on light backgrounds

# Fade animation durations in milliseconds.
_FADE_IN_MS: int = 150
_FADE_OUT_MS: int = 200


class LoadingOverlay(QWidget):
    """Semi-transparent overlay with a fade-in / fade-out animation that covers
    its parent while a task is loading.

    The overlay is created as a direct child of *parent* and fills it
    completely.  It installs an event filter on *parent* so it automatically
    stays aligned when the parent is resized.  It starts hidden; call
    :meth:`start` to show it and :meth:`stop` to fade it away.

    Usage::

        self._loading = LoadingOverlay(self)

        # When the background task starts:
        self._loading.start("Fetching device info…")

        # When the result signal fires:
        self._loading.stop()

    Args:
        parent: The widget this overlay should cover.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LoadingOverlay")

        self._bg_color: QColor = QColor()
        self._spinner: LoadingSpinner
        self._message_label: QLabel
        self._effect: QGraphicsOpacityEffect
        self._fade_in: QPropertyAnimation
        self._fade_out: QPropertyAnimation

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

        # Track parent geometry changes so the overlay stays full-coverage.
        if parent is not None:
            parent.installEventFilter(self)

        # Start hidden; visible only after start() is called.
        self.hide()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self._create_widgets()
        self._setup_layout()
        self._setup_animations()

    def _create_widgets(self) -> None:
        self._spinner = LoadingSpinner(size=40)
        self._message_label = self._create_message_label()

    @staticmethod
    def _create_message_label() -> QLabel:
        # Centered muted text label rendered below the spinner.
        label = QLabel()
        label.setObjectName("loadingMessage")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _setup_layout(self) -> None:
        # Stack spinner and label vertically, centered in the overlay.
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(Spacing.SM)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._message_label, 0, Qt.AlignmentFlag.AlignHCenter)

    def _setup_animations(self) -> None:
        # QGraphicsOpacityEffect lets us animate the opacity of the entire
        # widget (including its paintEvent background) as an embedded child.
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

        self._fade_in = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade_in.setDuration(_FADE_IN_MS)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._fade_out = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade_out.setDuration(_FADE_OUT_MS)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InOutCubic)
        # Hide as soon as the fade-out animation completes.
        self._fade_out.finished.connect(self.hide)

    def _apply_style(self) -> None:
        # Set the semi-transparent background color for paintEvent.
        if theme_manager.is_dark:
            bg = QColor(Palette.DARK_900)
            bg.setAlpha(_DARK_BG_ALPHA)
        else:
            bg = QColor(LightPalette.DARK_900)
            bg.setAlpha(_LIGHT_BG_ALPHA)
        self._bg_color = bg

        # Apply QSS for the message label text color.
        qss = load_stylesheet(
            LoadingStyles.OVERLAY,
            themed([LoadingOverlayColors], [LightLoadingOverlayColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)
        self.update()

    def _connect_signals(self) -> None:
        theme_manager.theme_changed.connect(self._apply_style)

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self, message: str = "Loading…") -> None:
        """Cover the parent widget and start the spinner animation.

        Positions the overlay to fill its parent, sets the loading message,
        raises it above sibling widgets, and fades it in smoothly.

        Args:
            message: Short description shown below the spinner.  Pass an empty
                string to render the spinner alone with no label.
        """
        self._message_label.setText(message)
        self._message_label.setVisible(bool(message))

        # Align geometry to parent before becoming visible.
        if self.parent() is not None:
            self.setGeometry(self.parent().rect())  # type: ignore[union-attr]

        # Cancel any in-progress fade-out and reset opacity before fading in.
        self._fade_out.stop()
        self._effect.setOpacity(0.0)

        self.show()
        self.raise_()
        self._fade_in.start()

    def stop(self) -> None:
        """Fade out and hide the overlay.

        Safe to call when the overlay is already hidden — silently no-ops.
        """
        if not self.isVisible():
            return
        self._fade_in.stop()
        self._fade_out.start()

    # ── Event filter ───────────────────────────────────────────────────────────

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Keep overlay geometry in sync when the parent widget is resized.

        Args:
            watched: The object that generated the event.
            event:   The event being processed.

        Returns:
            Always ``False`` — this filter observes only; it never consumes events.
        """
        if watched is self.parent() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parent().rect())  # type: ignore[union-attr]
        return super().eventFilter(watched, event)

    # ── Background paint ───────────────────────────────────────────────────────

    def paintEvent(self, event: QPaintEvent) -> None:
        """Fill the overlay with the semi-transparent surface color.

        Args:
            event: The paint event.
        """
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._bg_color)

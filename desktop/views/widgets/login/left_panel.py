import sys

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

import utils.styles
from app.theme_manager import theme_manager
from resources.colors import LoginColors, LightLoginColors, Colors, LightColors
from resources.paths import LoginStyles
from utils.styles import themed
from resources.spacing import Spacing
from views.widgets.indicators.pulsing_dot import PulsingDot
from views.widgets.logo_widget import Logo, LogoNameLabel


class _BtSonarWidget(QWidget):
    """Sonar-ping animation used as the Bluetooth waiting indicator.

    Rings emanate outward from a central Bluetooth icon and fade as they grow,
    signalling that the PC is actively scanning for a device. The timer runs
    only while the widget is visible (stopped in WiFi mode).
    """

    _ACCENT = QColor(Colors.ACCENT_PRIMARY)
    _SIZE = 120
    _CENTER = 60.0
    _MIN_RADIUS = 18.0     # ring birth radius (just outside the core disc)
    _MAX_RADIUS = 56.0     # ring death radius (near the widget edge)
    _RING_COUNT = 3        # concurrent expanding rings (staggered)
    _SPEED = 0.012         # progress per tick → controls ping rate

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self._SIZE, self._SIZE)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps
        self._timer.timeout.connect(self._tick)

    def showEvent(self, event) -> None:  # noqa: N802
        # Start the ping loop only while the Bluetooth panel is visible.
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        # Stop the loop in WiFi mode so the hidden widget costs zero CPU.
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        self._phase = (self._phase + self._SPEED) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Expanding sonar rings, staggered evenly across the cycle.
        for i in range(self._RING_COUNT):
            progress = (self._phase + i / self._RING_COUNT) % 1.0
            radius = self._MIN_RADIUS + progress * (self._MAX_RADIUS - self._MIN_RADIUS)
            color = QColor(self._ACCENT)
            color.setAlpha(int(180 * (1.0 - progress)))  # fade as it grows
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(self._CENTER - radius, self._CENTER - radius,
                                       radius * 2, radius * 2))

        # Static central disc — the 'source' of the pings.
        disc = QColor(self._ACCENT)
        disc.setAlpha(int(255 * 0.16))
        painter.setPen(QPen(self._ACCENT, 1))
        painter.setBrush(disc)
        painter.drawEllipse(QRectF(self._CENTER - 16, self._CENTER - 16, 32, 32))

        # BT rune centered.
        painter.setPen(QPen(self._ACCENT))
        painter.setFont(QFont("Segoe UI Symbol", 20))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "ᛒ")


class LeftPanel(QWidget):
    """Left panel of the login screen. Displays the Bluetooth waiting indicator."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._logo: Logo
        self._logo_name: LogoNameLabel
        self._app_description: QLabel

        self._bt_icon_label: QWidget
        self._bt_title: QLabel
        self._bt_instructions: QLabel

        self._waiting_for_connection: QWidget
        self._bt_content: QWidget

        self._setup_ui()
        self._setup_style()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("LeftPanel")
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        self._logo = self._create_logo()
        self._logo_name = self._create_logo_name()
        self._app_description = self._create_description()

        self._bt_icon_label = _BtSonarWidget()
        self._bt_title = self._create_bt_title()
        self._bt_instructions = self._create_bt_instructions()
        self._bt_content = self._build_bt_content()

        self._waiting_for_connection = self._create_waiting_for_connection_widget()

    def _setup_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.SM, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.SM)

        layout.addStretch(1)

        layout.addWidget(self._logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._logo_name, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._app_description, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacing(Spacing.MD)

        layout.addWidget(self._bt_content)

        layout.addSpacing(Spacing.SM)

        layout.addWidget(self._waiting_for_connection, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(3)

    # ── Content panel builders ─────────────────────────────────────────────────

    def _build_bt_content(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._bt_icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(Spacing.LG)
        layout.addWidget(self._bt_title, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(Spacing.XS)
        layout.addWidget(self._bt_instructions, alignment=Qt.AlignmentFlag.AlignHCenter)
        return widget

    # ── Widget factories ───────────────────────────────────────────────────────

    @staticmethod
    def _create_logo() -> Logo:
        return Logo(logo_size=100)

    def _create_description(self) -> QLabel:
        label = QLabel(self)
        label.setText("Seamless cross-device connectivity")
        label.setObjectName("DescriptionLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    @staticmethod
    def _create_logo_name() -> LogoNameLabel:
        logo_label = LogoNameLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setObjectName("LogoName")
        return logo_label

    @staticmethod
    def _create_bt_title() -> QLabel:
        label = QLabel("Waiting for Bluetooth connection…")
        label.setObjectName("BtTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    @staticmethod
    def _create_bt_instructions() -> QLabel:
        label = QLabel("Open SyncDose on your phone\nand tap Scan Nearby Devices to connect")
        label.setObjectName("DetailedScanInstructions")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _create_waiting_for_connection_widget() -> QWidget:
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(widget)
        indicator = PulsingDot()
        layout.addWidget(indicator)
        label = QLabel()
        label.setText("Waiting for connection…")
        label.setObjectName("WaitingForConnectionLabel")
        layout.addWidget(label)
        return widget

    # ── Style ──────────────────────────────────────────────────────────────────

    def _setup_style(self) -> None:
        qss = utils.styles.load_stylesheet(
            LoginStyles.LEFT_PANEL,
            themed([LoginColors, Colors], [LightLoginColors, LightColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        theme_manager.theme_changed.connect(self._setup_style)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    left_panel = LeftPanel()
    left_panel.show()
    app.exec()

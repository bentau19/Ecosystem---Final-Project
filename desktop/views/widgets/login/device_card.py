"""
Device card for the login screen's right panel.
Shows name, OS/tag meta, status badge, and last-seen time.
On hover the status column is replaced by a 'Connect →' button.
"""
from datetime import datetime, timedelta

from PySide6.QtCore import QEvent, QRectF, Qt, Signal, Slot
from PySide6.QtGui import QColor, QEnterEvent, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from dto.previous_device import PreviousDeviceDTO
from enums.device_status import DeviceStatus
from enums.screen import Screen
from resources.colors import LoginColors
from resources.paths import Icons
from resources.spacing import Spacing
from utils import viewmodel_manager
from utils.navigation_manager import navigation_manager
from viewmodels.device import DeviceViewModel

# Maps DeviceStatus → (QSS object name for badge, badge display text)
_BADGE_CONFIG: dict[DeviceStatus, str] = {
    DeviceStatus.RECENT: "BadgeRecent",
    DeviceStatus.IDLE: "BadgeIdle",
}

_ICON_SIZE: int = 48
_ICON_RADIUS: int = 12
_ICON_MARGIN: int = 9


class DeviceCard(QWidget):
    """Card widget for a single :class:`~dto.previous_device.PreviousDeviceDTO`.

    On hover, replaces the status column with a 'Connect →' button.
    Clicking the button calls the connectivity service directly via
    :data:`utils.services_manager.services_manager`.
    """

    def __init__(
            self,
            device: PreviousDeviceDTO,
            parent: QWidget | None = None,
    ) -> None:
        """
        Args:
            device: Device data to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._device = device

        self._icon_lbl: QLabel
        self._name_lbl: QLabel
        self._meta_lbl: QLabel
        self._badge: QLabel
        self._time_lbl: QLabel
        self._status_widget: QWidget
        self._connect_btn: QPushButton

        self._device_viewmodel: DeviceViewModel = viewmodel_manager.device_viewmodel

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setObjectName("DeviceCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    @property
    def device(self) -> PreviousDeviceDTO:
        """The device DTO bound to this card."""
        return self._device

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        """Construct and arrange all child widgets."""
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        """Instantiate all child widgets."""
        self._icon_lbl = self._create_icon_label()

        self._name_lbl = QLabel(self._device.name)
        self._name_lbl.setObjectName("DeviceName")

        self._meta_lbl = QLabel(f"{self._device.os}  ·  {self._device.tag}")
        self._meta_lbl.setObjectName("DeviceMeta")

        time = datetime.strptime(self._device.last_connected, "%d-%m-%Y")

        obj_name = "BadgeRecent" if datetime.now() - time < timedelta(days=14) else "BadgeIdle"
        text = "recent" if datetime.now() - time < timedelta(days=14) else "idle"

        self._badge = QLabel(text)
        self._badge.setFixedWidth(50)
        self._badge.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._badge.setObjectName(obj_name)

        self._time_lbl = QLabel(self._device.last_connected)
        self._time_lbl.setObjectName("DeviceTime")
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        self._status_widget = self._create_status_container()

        self._connect_btn = QPushButton("Connect →")
        self._connect_btn.setObjectName("ConnectBtn")
        self._connect_btn.setVisible(False)

    def _create_icon_label(self) -> QLabel:
        """Render the device icon as a tinted rounded-square Pixmap.

        Derives the background color from the device ID so the same device
        always gets the same color, with no color stored in the data layer.

        Returns:
            A fixed-size QLabel containing the rendered Pixmap.
        """
        color = QColor(LoginColors.ICON_BG)

        pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rounded-square tinted background
        bg_path = QPainterPath()
        bg_path.addRoundedRect(0, 0, _ICON_SIZE, _ICON_SIZE, _ICON_RADIUS, _ICON_RADIUS)
        painter.fillPath(bg_path, color)

        # SVG icon overlay — all device cards use the smartphone icon
        renderer = QSvgRenderer(Icons.SMARTPHONE)
        m = _ICON_MARGIN
        renderer.render(painter, QRectF(m, m, _ICON_SIZE - m * 2, _ICON_SIZE - m * 2))

        painter.end()

        lbl = QLabel(self)
        lbl.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        lbl.setPixmap(pixmap)
        return lbl

    def _create_status_container(self) -> QWidget:
        """Wrap badge and time label in a right-aligned column widget.

        Returns:
            A QWidget containing the badge and last-seen label stacked vertically.
        """
        container = QWidget(self)
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        col = QVBoxLayout(container)
        col.setSpacing(Spacing.XS)
        col.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        col.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignRight)
        col.addWidget(self._time_lbl, alignment=Qt.AlignmentFlag.AlignRight)
        return container

    def _setup_layout(self) -> None:
        """Arrange all child widgets in a horizontal row."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.LG)

        layout.addWidget(self._icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(Spacing.XS)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.addWidget(self._name_lbl)
        text_col.addWidget(self._meta_lbl)

        layout.addLayout(text_col)
        layout.addStretch()
        layout.addWidget(self._status_widget)
        layout.addWidget(self._connect_btn)

    def _apply_style(self) -> None:
        """No per-card stylesheet — styles are inherited from RightPanel."""
        pass

    def _connect_signals(self) -> None:
        """Wire the Connect button to the connection handler."""
        self._connect_btn.clicked.connect(self._on_button_clicked)
        self._device_viewmodel.device_connected.connect(self._on_device_connected)
        pass

    # ── Hover events ──────────────────────────────────────────────────────────

    def enterEvent(self, event: QEnterEvent) -> None:
        """Swap status column for the Connect button on mouse enter.

        Args:
            event: The enter event.
        """
        self._status_widget.setVisible(False)
        self._connect_btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """Restore status column and hide Connect button on mouse leave.

        Args:
            event: The leave event.
        """
        self._connect_btn.setVisible(False)
        self._status_widget.setVisible(True)
        super().leaveEvent(event)

    @Slot(object)
    def _on_device_connected(self, prev: PreviousDeviceDTO) -> None:
        """Forward a card's connection request as a panel-level signal.

        Args:
            prev: The DTO of the device the user wishes to connect to.

        Emits:
            device_connect_requested: Re-emits the same DTO upstream.
        """
        navigation_manager.go_to_screen(Screen.DASHBOARD)

    @Slot()
    def _on_button_clicked(self):
        self._device_viewmodel.connect_device(self._device.ip)

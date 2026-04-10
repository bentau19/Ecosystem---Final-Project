"""
Device card for the login screen's right panel.
Shows name, OS/tag meta, status badge, and last-seen time.
On hover the status column is replaced by a 'Connect →' button.
"""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from dto.previous_device import PreviousDeviceDTO
from enums.device_status import DeviceStatus
from resources.spacing import Spacing
from views.widgets.login.device_icon import DeviceIcon

# Maps DeviceStatus → (QSS object name for badge, badge display text)
_BADGE_CONFIG: dict[DeviceStatus, tuple[str, str]] = {
    DeviceStatus.ONLINE: ("BadgeOnline", "online"),
    DeviceStatus.RECENT: ("BadgeRecent", "2m ago"),
    DeviceStatus.IDLE:   ("BadgeIdle",   "idle"),
}


class DeviceCard(QWidget):
    """
    Card widget for a single :class:`~entities.previous_device.PreviousDeviceEntity`.

    Emits :attr:`connect_requested` (with the entity) when 'Connect →' is clicked.
    """

    connect_requested: Signal = Signal(object)

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

        self._icon: DeviceIcon
        self._name_lbl: QLabel
        self._meta_lbl: QLabel
        self._badge: QLabel
        self._time_lbl: QLabel
        self._status_widget: QWidget
        self._connect_btn: QPushButton

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
        self._icon = DeviceIcon(self._device.icon_color, self)

        self._name_lbl = QLabel(self._device.name)
        self._name_lbl.setObjectName("DeviceName")

        self._meta_lbl = QLabel(f"{self._device.os_label}  ·  {self._device.tag}")
        self._meta_lbl.setObjectName("DeviceMeta")

        obj_name, badge_text = _BADGE_CONFIG[self._device.status]
        self._badge = QLabel(badge_text)
        self._badge.setObjectName(obj_name)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._time_lbl = QLabel(self._device.last_seen)
        self._time_lbl.setObjectName("DeviceTime")
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        self._status_widget = self._create_status_container()

        self._connect_btn = QPushButton("Connect →")
        self._connect_btn.setObjectName("ConnectBtn")
        self._connect_btn.setVisible(False)

    def _create_status_container(self) -> QWidget:
        """Wrap badge and time label in a right-aligned column widget.

        Returns:
            A QWidget containing the badge and last-seen label stacked vertically.
        """
        container = QWidget(self)
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        col = QVBoxLayout(container)
        col.setSpacing(Spacing.XS)
        col.setContentsMargins(0, 0, 0, 0)
        col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        col.addWidget(self._badge)
        col.addWidget(self._time_lbl)
        return container

    def _setup_layout(self) -> None:
        """Arrange all child widgets in a horizontal row."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.LG)

        layout.addWidget(self._icon)

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
        """Wire the Connect button to emit connect_requested."""
        self._connect_btn.clicked.connect(
            lambda: self.connect_requested.emit(self._device)
        )

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

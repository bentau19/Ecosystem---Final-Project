"""
Right panel of the login screen — 'Previously connected' device list.
"""

from PySide6.QtCore import Qt, QRectF, Slot
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

import utils.styles
from dto.previous_device import PreviousDeviceDTO
from enums.screen import Screen
from resources.colors import Palette
from resources.paths import Icons, LoginStyles
from resources.spacing import Spacing
from utils.viewmodel_manager import viewmodel_manager
from utils.navigation_manager import NavigationManager, navigation_manager
from viewmodels.device import DeviceViewModel
from views.widgets.login.previous_device_card import PreviousDeviceCard


# Empty-state icon dimensions — mirrors the HTML .device-icon CSS rule
_EMPTY_ICON_SIZE: int   = 40   # CSS: width/height 40px
_EMPTY_ICON_RADIUS: int = 10   # CSS: border-radius 10px
_EMPTY_ICON_MARGIN: int = 8    # SVG natural size 24px → (40-24)/2 = 8px padding


class RightPanel(QWidget):
    """Right-side panel of the login screen.

    Displays a title, a list of :class:`~views.widgets.login.previous_device_card.PreviousDeviceCard`
    widgets for previously connected devices, and an 'End-to-end encrypted' footer.
    When no previous devices exist, shows a centered empty-state message instead.

    Device cards are populated via :class:`~viewmodels.device.DeviceViewModel`;
    this panel owns no signals of its own — navigation is handled by
    :data:`~utils.navigation_manager.navigation_manager` inside each card.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._cards: list[PreviousDeviceCard] = []

        self._title_lbl: QLabel
        self._subtitle_lbl: QLabel
        self._device_list: QWidget
        self._device_list_layout: QVBoxLayout
        self._empty_state: QWidget
        self._footer: QWidget
        self._privacy_lbl: QLabel
        self._help_lbl: QLabel

        self._device_viewmodel: DeviceViewModel = viewmodel_manager.device_viewmodel
        self._navigation_manager: NavigationManager = navigation_manager

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("RightPanel")

        self._setup_ui()
        self._apply_style()
        self._connect_signals()
        self._device_viewmodel.load_devices()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        """Construct and arrange all child widgets."""
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        """Instantiate all child widgets."""
        self._title_lbl = QLabel("Previously connected")
        self._title_lbl.setObjectName("RightPanelTitle")

        self._subtitle_lbl = QLabel("Tap a device to reconnect instantly")
        self._subtitle_lbl.setObjectName("RightPanelSubtitle")

        self._device_list = self._create_device_list()
        self._empty_state = self._create_empty_state()
        self._footer = self._create_footer()

    def _create_device_list(self) -> QWidget:
        """Build an empty container that will be populated via the ViewModel.

        Returns:
            A QWidget whose layout receives one DeviceCard per loaded device.
        """
        container = QWidget(self)
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        container.setObjectName("DeviceList")

        self._device_list_layout = QVBoxLayout(container)
        self._device_list_layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        self._device_list_layout.setSpacing(Spacing.SM)

        return container

    def _create_empty_state(self) -> QWidget:
        """Build a centered empty-state widget shown when no previous devices exist.

        Returns:
            A QWidget with an icon, heading, and hint text vertically centered.
        """
        container = QWidget(self)
        container.setObjectName("NoDevicesView")
        # Allow the container to expand so internal stretches can center the content
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        layout.setSpacing(Spacing.NONE)

        # Icon — glowing rounded-square container with cyan smartphone SVG
        icon_lbl = QLabel()
        icon_lbl.setObjectName("EmptyStateIcon")
        icon_lbl.setFixedSize(_EMPTY_ICON_SIZE, _EMPTY_ICON_SIZE)
        icon_lbl.setPixmap(self._create_icon_pixmap())
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_lbl = QLabel("No devices connected previously")
        title_lbl.setObjectName("EmptyStateTitle")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle_lbl = QLabel("Scan the QR code on the left to connect your first device")
        subtitle_lbl.setObjectName("EmptyStateSubtitle")
        subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_lbl.setWordWrap(True)

        # Vertical centering via flanking stretches
        layout.addStretch()
        layout.addWidget(icon_lbl)
        layout.addSpacing(Spacing.LG)
        layout.addWidget(title_lbl)
        layout.addSpacing(Spacing.XS)
        layout.addWidget(subtitle_lbl)
        layout.addStretch()

        # Start hidden; _on_devices_loaded decides which state to show
        container.setVisible(False)

        return container

    def _create_footer(self) -> QWidget:
        """Build the 'End-to-end encrypted · Privacy · Help' footer row.

        Returns:
            A QWidget containing the footer labels laid out horizontally.
        """
        footer = QWidget(self)
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        layout.setSpacing(Spacing.XS)

        encrypted_lbl = QLabel("End-to-end encrypted ·")
        encrypted_lbl.setObjectName("FooterText")

        self._privacy_lbl = QLabel("Privacy")
        self._privacy_lbl.setObjectName("FooterLink")
        self._privacy_lbl.setCursor(Qt.CursorShape.PointingHandCursor)

        sep_lbl = QLabel("·")
        sep_lbl.setObjectName("FooterText")

        self._help_lbl = QLabel("Help")
        self._help_lbl.setObjectName("FooterLink")
        self._help_lbl.setCursor(Qt.CursorShape.PointingHandCursor)

        layout.addStretch()
        layout.addWidget(encrypted_lbl)
        layout.addWidget(self._privacy_lbl)
        layout.addWidget(sep_lbl)
        layout.addWidget(self._help_lbl)

        return footer

    def _create_icon_pixmap(self) -> QPixmap:
        """Render the empty-state smartphone icon.

        Translates the HTML ``.device-icon`` CSS rule into a QPainter pixmap:
        - background: ``oklch(1 0 0 / 0.04)``  → white at 4 % opacity
        - border:     ``1px solid --line-2``    → :data:`Palette.GRAY_640`
        - border-radius: 10 px
        - icon color: ``--text-2``              → SVG stroke (cyan accent)

        Returns:
            A fully rendered QPixmap ready to be set on a QLabel.
        """
        s = _EMPTY_ICON_SIZE
        r = _EMPTY_ICON_RADIUS
        m = _EMPTY_ICON_MARGIN

        pixmap = QPixmap(s, s)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 0.5 px inset so the 1 px stroke sits fully within the pixmap boundary
        rect = QRectF(0.5, 0.5, s - 1.0, s - 1.0)
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)

        # background: oklch(1 0 0 / 0.04) — white at ~4 % opacity
        painter.setBrush(QColor(255, 255, 255, 10))
        # border: 1px solid --line-2
        painter.setPen(QPen(QColor(Palette.GRAY_640), 1.0))
        painter.drawPath(path)

        # icon centered — SVG stroke carries the --text-2 colour
        renderer = QSvgRenderer(Icons.SMARTPHONE)
        renderer.render(painter, QRectF(m, m, s - m * 2, s - m * 2))

        painter.end()
        return pixmap

    def _setup_layout(self) -> None:
        """Arrange all child widgets in a vertical column."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.SM)

        layout.addWidget(self._title_lbl)
        layout.addWidget(self._subtitle_lbl)
        layout.addSpacing(Spacing.MD)
        # device_list has no stretch — cards keep their natural height.
        # empty_state uses a large stretch factor so it fills virtually all
        # remaining space when visible. Qt excludes hidden widgets from stretch
        # distribution, so addStretch() below handles the footer gap when
        # device_list is shown and empty_state is hidden.
        layout.addWidget(self._device_list)
        layout.addWidget(self._empty_state, 1000)
        layout.addStretch()
        layout.addWidget(self._footer)

    def _apply_style(self) -> None:
        """Load and apply the right-panel QSS stylesheet."""
        qss = utils.styles.load_stylesheet(LoginStyles.RIGHT_PANEL)
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        """Connect ViewModel signals to their handler slots.

        The initial device load is triggered separately in ``__init__`` after
        this method returns, ensuring the slot is already wired before the
        signal fires.
        """
        self._device_viewmodel.previous_devices_updated.connect(self._on_devices_loaded)

    # ── Slots ──────────────────────────────────────────────────────────────────

    @Slot(list)
    def _on_devices_loaded(self, dtos: list[PreviousDeviceDTO]) -> None:
        """Populate the device list from ViewModel data, or show empty state.

        Clears any previously rendered cards, then creates one
        :class:`DeviceCard` per DTO and wires its connect signal.
        Toggles the empty-state widget and subtitle visibility based on
        whether any devices were loaded.

        Args:
            dtos: The list of device DTOs emitted by the ViewModel.
        """
        has_devices = bool(dtos)

        # Toggle subtitle — irrelevant when no devices exist
        self._subtitle_lbl.setVisible(has_devices)

        # Clear existing cards
        for card in self._cards:
            self._device_list_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        # Populate with fresh cards
        for dto in dtos:
            card = PreviousDeviceCard(dto, parent=self._device_list)
            card.setMinimumWidth(400)
            self._cards.append(card)
            self._device_list_layout.addWidget(card)

        # Show the appropriate middle section
        self._device_list.setVisible(has_devices)
        self._empty_state.setVisible(not has_devices)

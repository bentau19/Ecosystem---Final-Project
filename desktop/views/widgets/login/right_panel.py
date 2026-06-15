from PySide6.QtCore import Qt, QRectF, Slot
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

import utils.styles
from app.theme_manager import theme_manager
from domain.dto.previous_device import PreviousDeviceDTO
from resources.colors import Palette, LoginColors, LightLoginColors, Colors, LightColors, LightPalette
from resources.paths import Icons, LoginStyles
from utils.styles import themed
from resources.spacing import Spacing
from app.app_state import app_state
from app.navigation_manager import NavigationManager, navigation_manager
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
    :data:`~app.navigation_manager.navigation_manager` inside each card.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the right panel and build its content layout.

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

        self._device_viewmodel: DeviceViewModel = app_state.device_viewmodel
        self._navigation_manager: NavigationManager = navigation_manager

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("RightPanel")

        self._setup_ui()
        self._apply_style()
        self._connect_signals()
        self._device_viewmodel.load_devices()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        # Create widgets and build the panel layout.
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        # Instantiate title, subtitle, device list, empty-state, and footer.
        self._title_lbl = QLabel("Previously connected")
        self._title_lbl.setObjectName("RightPanelTitle")

        self._subtitle_lbl = QLabel("Tap a device to reconnect instantly")
        self._subtitle_lbl.setObjectName("RightPanelSubtitle")

        self._device_list = self._create_device_list()
        self._empty_state = self._create_empty_state()
        self._footer = self._create_footer()

    def _create_device_list(self) -> QWidget:
        # Empty on construction; populated by _on_devices_loaded when the ViewModel fires.
        container = QWidget(self)
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        container.setObjectName("DeviceList")

        self._device_list_layout = QVBoxLayout(container)
        self._device_list_layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        self._device_list_layout.setSpacing(Spacing.SM)

        return container

    def _create_empty_state(self) -> QWidget:
        # Build the no-devices placeholder with a centered icon, title, and subtitle.
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
        layout.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(Spacing.LG)
        layout.addWidget(title_lbl)
        layout.addSpacing(Spacing.XS)
        layout.addWidget(subtitle_lbl)
        layout.addStretch()

        # Start hidden; _on_devices_loaded decides which state to show
        container.setVisible(False)

        return container

    def _create_footer(self) -> QWidget:
        # Build the 'End-to-end encrypted · Privacy · Help' footer row.
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
        # Translates the HTML .device-icon CSS rule into a QPainter pixmap.
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

        # background: white at ~4% opacity
        painter.setBrush(QColor(255, 255, 255, 10))
        # border: 1px solid — pick from active palette so light mode renders a soft gray
        border_hex = Palette.GRAY_640 if theme_manager.is_dark else LightPalette.GRAY_640
        painter.setPen(QPen(QColor(border_hex), 1.0))
        painter.drawPath(path)

        # icon centered — SVG stroke carries the --text-2 colour
        renderer = QSvgRenderer(Icons.SMARTPHONE)
        renderer.render(painter, QRectF(m, m, s - m * 2, s - m * 2))

        painter.end()
        return pixmap

    def _setup_layout(self) -> None:
        # Stack title, subtitle, device list, empty-state, and footer vertically.
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
        # Load and apply the themed right-panel QSS.
        qss = utils.styles.load_stylesheet(
            LoginStyles.RIGHT_PANEL,
            themed([LoginColors, Colors], [LightLoginColors, LightColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        # Wire before load_devices() is called in __init__ so the signal never fires
        # before the slot is connected.
        self._device_viewmodel.previous_devices_updated.connect(self._on_devices_loaded)
        theme_manager.theme_changed.connect(self._apply_style)

    # ── Slots ──────────────────────────────────────────────────────────────────

    @Slot(list)
    def _on_devices_loaded(self, dtos: list[PreviousDeviceDTO]) -> None:
        # Clear existing cards, populate with fresh ones, then toggle empty-state visibility.
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

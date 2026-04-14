"""
Right panel of the login screen — 'Previously connected' device list.
"""

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

import utils.styles
from dto.previous_device import PreviousDeviceDTO
from enums.screen import Screen
from resources.paths import Icons, LoginStyles
from resources.spacing import Spacing
from utils.viewmodel_manager import viewmodel_manager
from utils.navigation_manager import NavigationManager, navigation_manager
from viewmodels.device import DeviceViewModel
from views.widgets.login.device_card import DeviceCard


class RightPanel(QWidget):
    """
    Right-side panel of the login screen.

    Displays a title, a scrollable list of :class:`DeviceCard` widgets for
    previously connected devices, and an 'End-to-end encrypted' footer.
    When no previous devices exist, shows a centered empty-state message instead.

    Emits:
        device_connect_requested: Forwarded from each DeviceCard's
            connect_requested signal; carries the selected PreviousDeviceDTO.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._cards: list[DeviceCard] = []

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
        self._device_viewmodel.connect_device("1232")

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
        container.setObjectName("EmptyState")
        # Allow the container to expand so internal stretches can center the content
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        layout.setSpacing(Spacing.NONE)

        # Icon
        icon_lbl = QLabel()
        icon_lbl.setObjectName("EmptyStateIcon")
        pixmap = QPixmap(Icons.SMARTPHONE).scaled(
            48, 48,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        icon_lbl.setPixmap(pixmap)
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
        """Connect ViewModel signals and trigger the initial device load."""
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
            card = DeviceCard(dto, parent=self._device_list)
            card.setMinimumWidth(400)
            self._cards.append(card)
            self._device_list_layout.addWidget(card)

        # Show the appropriate middle section
        self._device_list.setVisible(has_devices)
        self._empty_state.setVisible(not has_devices)

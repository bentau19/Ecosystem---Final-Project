"""
Right panel of the login screen — 'Previously connected' device list.
"""

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

import utils.styles
from dto.previous_device import PreviousDeviceDTO
from resources.paths import LoginStyles
from resources.spacing import Spacing
from viewmodels.previous_device import PreviousDeviceViewModel
from views.widgets.login.device_card import DeviceCard


class RightPanel(QWidget):
    """
    Right-side panel of the login screen.

    Displays a title, a scrollable list of :class:`DeviceCard` widgets for
    previously connected devices, and an 'End-to-end encrypted' footer.

    Emits:
        device_connect_requested: Forwarded from each DeviceCard's
            connect_requested signal; carries the selected PreviousDeviceDTO.
    """

    device_connect_requested: Signal = Signal(object)  # emits PreviousDeviceDTO

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
        self._footer: QWidget
        self._privacy_lbl: QLabel
        self._help_lbl: QLabel

        self._prev_device_viewmodel: PreviousDeviceViewModel = PreviousDeviceViewModel()

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("RightPanel")

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

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
        self._device_list_layout.setContentsMargins(0, 0, 0, 0)
        self._device_list_layout.setSpacing(Spacing.SM)

        return container

    def _create_footer(self) -> QWidget:
        """Build the 'End-to-end encrypted · Privacy · Help' footer row.

        Returns:
            A QWidget containing the footer labels laid out horizontally.
        """
        footer = QWidget(self)
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 0)
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
        layout.addWidget(self._device_list)
        layout.addStretch()
        layout.addWidget(self._footer)

    def _apply_style(self) -> None:
        """Load and apply the right-panel QSS stylesheet."""
        qss = utils.styles.load_stylesheet(LoginStyles.RIGHT_PANEL)
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        """Connect ViewModel signals and trigger the initial device load."""
        # TODO: define what happens when clicking privacy/help
        self._prev_device_viewmodel.devices_loaded.connect(self._on_devices_loaded)
        self._prev_device_viewmodel.load_devices()

    # ── Slots ──────────────────────────────────────────────────────────────────

    @Slot(list)
    def _on_devices_loaded(self, dtos: list[PreviousDeviceDTO]) -> None:
        """Populate the device list from ViewModel data.

        Clears any previously rendered cards, then creates one
        :class:`DeviceCard` per DTO and wires its connect signal.

        Args:
            dtos: The list of device DTOs emitted by the ViewModel.
        """
        # Clear existing cards
        for card in self._cards:
            self._device_list_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        print(dtos)
        # Populate with fresh cards
        for dto in dtos:
            card = DeviceCard(dto, parent=self._device_list)
            self._cards.append(card)
            self._device_list_layout.addWidget(card)

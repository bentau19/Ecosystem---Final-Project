from PySide6.QtGui import QHideEvent
from PySide6.QtWidgets import QHBoxLayout, QWidget

from app.app_state import app_state
from app.navigation_manager import navigation_manager
from domain.enums.screen import Screen
from resources.spacing import Spacing
from views.widgets.loading.overlay import LoadingOverlay
from views.widgets.login.left_panel import LeftPanel


class LoginScreen(QWidget):
    """Login screen showing the QR-code / Bluetooth waiting panel.

    Connection is phone-initiated only — the phone scans the QR code or
    discovers the PC over Bluetooth and establishes the TCP handshake.  The
    PC never dials out, so no "previously connected" list is shown.

    A :class:`~views.widgets.loading.overlay.LoadingOverlay` covers the whole
    screen while a connection attempt is in progress. It starts on
    ``device_connecting`` (fired on both the QR and Bluetooth paths) and is
    hidden automatically when ``device_connected`` navigates away to the
    dashboard, triggering :meth:`hideEvent`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the login screen and build its layout.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._left_panel: LeftPanel
        self._loading_overlay: LoadingOverlay

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        self._left_panel = LeftPanel(self)
        # Overlay is created last so it sits above all sibling widgets in z-order.
        self._loading_overlay = LoadingOverlay(self)

    def _setup_layout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        layout.setSpacing(Spacing.NONE)
        layout.addWidget(self._left_panel)

    def _apply_style(self) -> None:
        # LeftPanel handles its own styling; no screen-level stylesheet needed.
        pass

    def _connect_signals(self) -> None:
        # device_connecting fires on both paths (QR and Bluetooth) and starts
        # the overlay. device_connected is the authoritative navigation trigger.
        # hideEvent resets the overlay to a clean state when the screen hides.
        vm = app_state.device_viewmodel
        vm.device_connecting.connect(lambda: self._loading_overlay.start("Connecting…"))
        vm.device_connected.connect(lambda: navigation_manager.go_to_screen(Screen.DASHBOARD))

    # ── Qt event overrides ────────────────────────────────────────────────────

    def hideEvent(self, event: QHideEvent) -> None:
        """Reset the loading overlay to a clean hidden state when navigation
        switches away from this screen.

        Args:
            event: The hide event delivered by Qt.
        """
        super().hideEvent(event)
        self._loading_overlay.hide()

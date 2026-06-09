from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import QHBoxLayout, QWidget

from app.app_state import app_state
from app.navigation_manager import navigation_manager
from domain.enums.screen import Screen
from resources.spacing import Spacing
from views.widgets.loading.overlay import LoadingOverlay
from views.widgets.login.left_panel import LeftPanel
from views.widgets.login.right_panel import RightPanel


class LoginScreen(QWidget):
    """Login screen composed of a left QR-code panel and a right
    'Previously connected' device list panel.

    The two panels share the full screen area in a fixed stretch ratio
    (2 : 1, left : right) with no margins or gap between them.

    A :class:`~views.widgets.loading.overlay.LoadingOverlay` covers the whole
    screen while a connection attempt is in progress. It starts on
    ``device_connecting`` (fired on both the button and QR paths) and is
    hidden automatically when ``device_connected`` navigates away to the
    dashboard, triggering :meth:`hideEvent`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the login screen and build its two-panel layout.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._left_panel: LeftPanel
        self._right_panel: RightPanel
        self._loading_overlay: LoadingOverlay

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        # Create the two panels and build their horizontal layout.
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        # Instantiate left (QR) and right (device list) panels, then the overlay.
        self._left_panel = LeftPanel(self)
        self._right_panel = RightPanel(parent=self)
        # Overlay is created last so it sits above all sibling widgets in z-order.
        self._loading_overlay = LoadingOverlay(self)

    def _setup_layout(self) -> None:
        # Place panels side-by-side; left is slightly narrower than right.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        layout.setSpacing(Spacing.NONE)

        # Left panel slightly narrower; right panel gets more space for card list
        layout.addWidget(self._left_panel, stretch=2)
        layout.addWidget(self._right_panel, stretch=1)

    def _apply_style(self) -> None:
        # Panels handle their own styling; no screen-level stylesheet needed.
        pass

    def _connect_signals(self) -> None:
        # device_connecting fires on both paths (button and QR) and starts the
        # overlay. device_connected fires once a TCP handshake succeeds and is
        # the authoritative trigger for navigation — owned here rather than in
        # PreviousDeviceCard so it works even when no previous devices exist in
        # the DB (zero cards → zero listeners otherwise). hideEvent then resets
        # the overlay to a clean state.
        vm = app_state.device_viewmodel
        vm.device_connecting.connect(lambda: self._loading_overlay.start("Connecting…"))
        vm.device_connected.connect(lambda: navigation_manager.go_to_screen(Screen.DASHBOARD))

    # ── Qt event overrides ────────────────────────────────────────────────────

    def showEvent(self, event: QShowEvent) -> None:
        """Reload the previous-devices list whenever the login screen becomes visible.

        Re-triggers :meth:`~viewmodels.device.DeviceViewModel.load_devices` so
        the right panel always reflects current DB state — including any device
        that was just connected and saved during the session the user is
        returning from.

        Args:
            event: The show event delivered by Qt.
        """
        super().showEvent(event)
        app_state.device_viewmodel.load_devices()

    def hideEvent(self, event: QHideEvent) -> None:
        """Reset the loading overlay to a clean hidden state when navigation
        switches away from this screen.

        Args:
            event: The hide event delivered by Qt.
        """
        super().hideEvent(event)
        self._loading_overlay.hide()

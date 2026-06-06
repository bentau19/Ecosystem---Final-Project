from PySide6.QtGui import QHideEvent
from PySide6.QtWidgets import QHBoxLayout, QWidget

from app.app_state import app_state
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
    ``device_connecting`` (button path) **or** ``device_connected`` (QR-scan
    path), and is hidden automatically when the screen is hidden by navigation.
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
        # Button path: device_connecting fires before the TCP handshake.
        # QR path:     device_connecting never fires; device_connected is the
        #              first event we get (from the background listener thread).
        # Both paths start the overlay. Navigation then hides the screen,
        # triggering hideEvent which resets the overlay to a clean state.
        vm = app_state.device_viewmodel
        vm.device_connecting.connect(lambda: self._loading_overlay.start("Connecting…"))
        vm.device_connected.connect(lambda: self._loading_overlay.start("Connecting…"))

    # ── Qt event overrides ────────────────────────────────────────────────────

    def hideEvent(self, event: QHideEvent) -> None:
        """Reset the loading overlay to a clean hidden state when navigation
        switches away from this screen.

        Args:
            event: The hide event delivered by Qt.
        """
        super().hideEvent(event)
        self._loading_overlay.hide()

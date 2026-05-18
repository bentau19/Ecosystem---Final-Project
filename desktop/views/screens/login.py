from PySide6.QtWidgets import QHBoxLayout, QWidget

from resources.spacing import Spacing
from views.widgets.login.left_panel import LeftPanel
from views.widgets.login.right_panel import RightPanel


class LoginScreen(QWidget):
    """
    Login screen composed of a left QR-code panel and a right
    'Previously connected' device list panel.

    The two panels share the full screen area in a fixed stretch ratio
    (5 : 6, left : right) with no margins or gap between them.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the login screen and build its two-panel layout.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._left_panel: LeftPanel
        self._right_panel: RightPanel

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        # Create the two panels and build their horizontal layout.
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        # Instantiate left (QR) and right (device list) panels.
        self._left_panel = LeftPanel(self)
        self._right_panel = RightPanel(parent=self)

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
        # No screen-level signals to wire; panels connect internally.
        pass

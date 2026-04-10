from PySide6.QtWidgets import QHBoxLayout, QWidget

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
        """
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
        """Construct and arrange child panels."""
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        """Instantiate the left and right panels."""
        self._left_panel = LeftPanel(self)
        self._right_panel = RightPanel(parent=self)

    def _setup_layout(self) -> None:
        """Place panels side by side with no margins or gap."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left panel slightly narrower; right panel gets more space for card list
        layout.addWidget(self._left_panel, stretch=5)
        layout.addWidget(self._right_panel, stretch=6)

    def _apply_style(self) -> None:
        """No screen-level stylesheet — panels handle their own styling."""
        pass

    def _connect_signals(self) -> None:
        """Wire up inter-panel signals."""
        pass

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout

from resources.spacing import Spacing
from views.widgets.divider import Divider
from views.widgets.navigation.sidebar import Sidebar
from views.widgets.settings.settings_content import SettingsContent
from views.widgets.topbar import Topbar


class SettingsScreen(QWidget):
    """Settings screen — mirrors the DashboardScreen layout.

    Composed of:
    - A :class:`~views.widgets.navigation.sidebar.Sidebar` with the "Settings"
      nav item active (``active_nav_index=1``).
    - A :class:`~views.widgets.topbar.Topbar` titled "Settings" with the
      standard disconnect button.
    - A :class:`~views.widgets.settings.settings_content.SettingsContent`
      scrollable area containing all configurable toggles.

    No loading overlay is needed — all settings are loaded synchronously
    from the local JSON file on startup.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the settings screen layout.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._sidebar: Sidebar
        self._topbar: Topbar
        self._settings_content: SettingsContent

        self._setup_ui()
        self.setWindowTitle("Settings")

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        # active_nav_index=1 highlights the "Settings" nav item in the sidebar.
        self._sidebar = Sidebar(logo_widget_height=100, active_nav_index=1)
        self._topbar = Topbar(topbar_height=100, title="Settings")
        self._settings_content = SettingsContent()

    def _setup_layout(self) -> None:
        # Right side: topbar + divider + settings content
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        right_layout.setSpacing(Spacing.NONE)
        right_layout.addWidget(self._topbar)
        right_layout.addWidget(Divider())
        right_layout.addWidget(self._settings_content)

        # Root: sidebar + right panel (matches DashboardScreen structure)
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        root_layout.setSpacing(Spacing.NONE)
        root_layout.addWidget(self._sidebar)
        root_layout.addWidget(right_panel)

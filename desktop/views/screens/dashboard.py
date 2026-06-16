from PySide6.QtCore import Slot
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QApplication
)

import resources_qrc  # noqa: F401
from app.app_state import app_state
from domain.dto.device_info import DeviceInfoDTO
from resources.spacing import Spacing
from views.widgets.dashboard.dashboard_content import DashboardContent
from views.widgets.divider import Divider
from views.widgets.loading.overlay import LoadingOverlay
from views.widgets.navigation.sidebar import Sidebar
from views.widgets.topbar import Topbar


class DashboardScreen(QWidget):
    """Main dashboard screen composed of a sidebar, topbar, divider, and content area.

    A :class:`~views.widgets.loading.overlay.LoadingOverlay` covers the full
    screen in two situations:

    * **Device-info loading** — shown every time the screen becomes visible
      (``showEvent``) and hidden once ``device_infos_updated`` fires.
      ``load_device_info()`` is re-triggered in ``showEvent`` so the signal
      always arrives *after* the overlay appears, regardless of when the
      initial background fetch completed.

    * **Logout** — shown when ``device_disconnecting`` fires. The
      ``_is_disconnecting`` guard prevents a stale queued ``device_infos_updated``
      (from the ``showEvent`` fetch) from stopping the "Disconnecting…" overlay
      prematurely. The overlay is cleaned up in ``hideEvent`` when navigation
      switches back to the login screen.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the dashboard screen and build its layout.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._dashboard_content: DashboardContent
        self._sidebar: Sidebar
        self._topbar: Topbar
        self._loading_overlay: LoadingOverlay
        # Guard: True while a disconnect is in progress so that a queued
        # device_infos_updated cannot stop the "Disconnecting…" overlay.
        self._is_disconnecting: bool = False

        self._set_up_ui()
        self._connect_signals()
        self.setWindowTitle("Dashboard")

    def _set_up_ui(self) -> None:
        # Create widgets and assemble the sidebar + main-area layout.
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        # Instantiate the content area, sidebar, topbar, and loading overlay.
        self._dashboard_content = DashboardContent()
        self._sidebar = Sidebar(logo_widget_height=100)
        self._topbar = Topbar(100)
        # Overlay is created last so raise_() puts it above all other children.
        self._loading_overlay = LoadingOverlay(self)

    def _setup_layout(self) -> None:
        # Right side: topbar + divider + content
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        right_layout.setSpacing(Spacing.NONE)
        right_layout.addWidget(self._topbar)
        right_layout.addWidget(Divider())
        right_layout.addWidget(self._dashboard_content)

        # Root: sidebar + right panel
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        root_layout.setSpacing(Spacing.NONE)
        root_layout.addWidget(self._sidebar)
        root_layout.addWidget(right_panel)

    def _connect_signals(self) -> None:
        # Wire device ViewModel signals to the loading overlay.
        vm = app_state.device_viewmodel
        # Stop the device-info overlay once fresh data arrives — guarded so a
        # stale queued update cannot kill the "Disconnecting…" overlay.
        vm.device_infos_updated.connect(self._on_device_infos_updated)
        # Stop the overlay on a channel-read error so the spinner never hangs.
        vm.device_info_error.connect(self._on_device_info_error)
        # Logout: show overlay and set guard when disconnect starts.
        vm.device_disconnecting.connect(self._on_device_disconnecting)
        # device_disconnected → navigation (Topbar._move_to_login) → hideEvent
        # handles cleanup; no direct connection to overlay.stop needed here.

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot(object)
    def _on_device_infos_updated(self, infos: list[DeviceInfoDTO]) -> None:
        # Stop the loading overlay only when not in the middle of a disconnect.
        # A queued device_infos_updated from the showEvent fetch could arrive
        # after device_disconnecting starts the logout overlay; the
        # _is_disconnecting flag blocks that race.
        if not self._is_disconnecting:
            self._loading_overlay.stop()

    @Slot(str)
    def _on_device_info_error(self, _error: str) -> None:
        # Stop the overlay so the user isn't left staring at a spinner.
        # The error is already logged by DeviceInfoService; the dashboard will
        # show stale DB data from the previous fetch which is preferable to
        # an indefinitely spinning overlay.
        if not self._is_disconnecting:
            self._loading_overlay.stop()

    @Slot()
    def _on_device_disconnecting(self) -> None:
        # Activate the logout overlay and arm the disconnect guard.
        self._is_disconnecting = True
        self._loading_overlay.start("Disconnecting…")

    # ── Qt event overrides ────────────────────────────────────────────────────

    def showEvent(self, event: QShowEvent) -> None:
        """Refresh all dashboard data whenever the screen becomes visible.

        Re-triggers device-info and tool loads so every widget always reflects
        current state on each visit — whether it's the first connect or a
        return after logout/reconnect.

        The device-info overlay stays up until ``device_infos_updated`` fires;
        tool data re-emits synchronously from the ViewModel's in-memory cache
        so the grid and header update instantly with no visible flash.

        Args:
            event: The show event delivered by Qt.
        """
        super().showEvent(event)
        self._loading_overlay.start("Fetching device info…")
        app_state.device_viewmodel.load_current_device_info()
        app_state.tool_viewmodel.load_enabled_tools()

    def hideEvent(self, event: QHideEvent) -> None:
        """Reset overlay and disconnect guard when navigation hides this screen.

        Args:
            event: The hide event delivered by Qt.
        """
        super().hideEvent(event)
        self._is_disconnecting = False
        self._loading_overlay.hide()


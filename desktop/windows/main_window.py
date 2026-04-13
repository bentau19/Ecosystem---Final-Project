from PySide6.QtCore import Slot
from PySide6.QtGui import QCloseEvent, QIcon, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMenu, QStackedWidget,
    QSystemTrayIcon, QWidget,
)

import utils.styles
from resources.paths import Icons, Styles
from utils.services_manager import services_manager
from views.screens.dashboard import DashboardScreen
from views.screens.login import LoginScreen


class MainWindow(QMainWindow):
    """Main application window — manages screen navigation via QStackedWidget."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stack: QStackedWidget
        self._login_screen: LoginScreen
        self._dashboard_screen: DashboardScreen
        self._tray_icon: QSystemTrayIcon

        self._setup_ui()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        """Build the stacked widget, register both screens, and set up the tray."""
        self._stack = QStackedWidget(self)

        self._login_screen = LoginScreen(self)
        self._dashboard_screen = DashboardScreen()

        self._stack.addWidget(self._login_screen)  # index 0 — shown on launch
        self._stack.addWidget(self._dashboard_screen)  # index 1

        self.setCentralWidget(self._stack)
        self._setup_tray()

    def _setup_tray(self) -> None:
        """Create the system tray icon with a context menu."""
        self._tray_icon = QSystemTrayIcon(QIcon(Icons.LOGO), parent=self)
        self._tray_icon.setToolTip("SyncDose")

        # Context menu: Open + Quit
        tray_menu = QMenu()
        tray_menu.setStyleSheet(utils.styles.load_stylesheet(Styles.TRAY_MENU))
        open_action = tray_menu.addAction("Open SyncDose")
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Quit")

        open_action.triggered.connect(self._restore_window)
        quit_action.triggered.connect(QApplication.quit)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _connect_signals(self) -> None:
        """Wire connectivity service signals to navigation slots."""
        services_manager.connectivity_service.device_connected.connect(self._show_dashboard)
        services_manager.connectivity_service.device_disconnected.connect(self._show_login)

    # ── Close → tray ──────────────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:
        """Intercept window close — hide to tray instead of quitting."""
        event.ignore()
        self.hide()

        self._tray_icon.showMessage(
            "SyncDose",
            "Running in the background. Right-click the tray icon to quit.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,  # ms
        )

    # ── Slots ──────────────────────────────────────────────────────────────────

    @Slot()
    def _show_dashboard(self) -> None:
        """Switch to the dashboard screen."""
        self._stack.setCurrentWidget(self._dashboard_screen)

    @Slot()
    def _show_login(self) -> None:
        """Switch back to the login screen."""
        self._stack.setCurrentWidget(self._login_screen)

    @Slot()
    def _restore_window(self) -> None:
        """Show and bring the main window to the foreground."""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Restore window on double-click of the tray icon."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_window()

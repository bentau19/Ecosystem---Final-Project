from PySide6.QtCore import Slot
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMenu, QStackedWidget,
    QSystemTrayIcon, QWidget,
)

import utils.styles
from enums.screen import Screen
from resources.paths import Icons, Styles
from utils.navigation_manager import navigation_manager, NavigationManager
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

        self._navigation_manager: NavigationManager = navigation_manager
        self._screens: list[QWidget]

        self._setup_ui()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        """Build the stacked widget, register both screens, and set up the tray."""
        self._stack = QStackedWidget(self)

        self._screens: dict[Screen, QWidget] = {
            Screen.LOGIN: LoginScreen(),
            Screen.DASHBOARD: DashboardScreen()
        }

        for screen in self._screens.values():
            self._stack.addWidget(screen)

        self.setCentralWidget(self._stack)
        self._setup_tray()
        self._connect_signals()

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
        self._navigation_manager.navigate.connect(self._change_page)

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

    @Slot(int)
    def _change_page(self, index: int) -> None:
        """Switch the stacked widget to the screen at the given index."""
        self._stack.setCurrentIndex(index)

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

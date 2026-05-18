from PySide6.QtCore import Slot, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMenu, QStackedWidget,
    QSystemTrayIcon, QWidget,
)

import utils.styles
from app.app_state import app_state
from app.theme_manager import theme_manager
from resources.colors import Colors, LightColors
from utils.styles import themed
from domain.enums.screen import Screen
from resources.paths import Icons, Styles
from app.navigation_manager import navigation_manager, NavigationManager
from views.screens.dashboard import DashboardScreen
from views.screens.login import LoginScreen
from views.widgets.dialogs.file_handler import TransferErrorDialog
from views.widgets.toasts.file_received import FileReceivedToast


class MainWindow(QMainWindow):
    """Main application window for SyncDose.

    Hosts a :class:`~PySide6.QtWidgets.QStackedWidget` that switches between
    the login screen and the dashboard screen. Navigation is driven entirely by
    :data:`~app.navigation_manager.navigation_manager` — nothing in this
    class decides *when* to change screens.

    Also manages the system tray icon so the user can reopen the window after
    minimizing it, and hides the window to the tray on minimize rather than
    closing it.

    Navigation is driven by :data:`~app.navigation_manager.navigation_manager`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Set up the window, screens, and system tray.

        Args:
            parent: Optional parent widget (typically ``None`` for a top-level window).
        """
        super().__init__(parent)
        self._stack: QStackedWidget
        self._login_screen: LoginScreen
        self._dashboard_screen: DashboardScreen
        self._tray_icon: QSystemTrayIcon
        self._tray_menu: QMenu

        self._navigation_manager: NavigationManager = navigation_manager
        self._screens: dict[Screen, QWidget]

        self._file_transfer_vm = app_state.file_transfer_viewmodel

        self._setup_ui()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────
    def _setup_ui(self) -> None:
        # Build the stacked widget, add screens, set as central, and configure the tray.
        self._stack = QStackedWidget(self)

        self._screens = {
            Screen.LOGIN: LoginScreen(),
            Screen.DASHBOARD: DashboardScreen()
        }

        for screen in self._screens.values():
            self._stack.addWidget(screen)

        self.setCentralWidget(self._stack)
        self._setup_tray()

    def _setup_tray(self) -> None:
        # Create the system-tray icon with an Open + Quit context menu.
        self._tray_icon = QSystemTrayIcon(QIcon(Icons.LOGO), parent=self)
        self._tray_icon.setToolTip("SyncDose")

        # Context menu: Open + Quit
        self._tray_menu = QMenu()
        self._restyle_tray()
        open_action = self._tray_menu.addAction("Open SyncDose")
        self._tray_menu.addSeparator()
        quit_action = self._tray_menu.addAction("Quit")

        open_action.triggered.connect(self._restore_window)
        quit_action.triggered.connect(QApplication.quit)

        self._tray_icon.setContextMenu(self._tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _connect_signals(self) -> None:
        # Wire navigation, file-transfer, and theme signals to their slots.
        self._navigation_manager.navigate.connect(self._change_page)
        self._file_transfer_vm.receive_error.connect(self._on_file_receive_error)
        self._file_transfer_vm.metadata_received.connect(self._on_file_received_metadata)
        theme_manager.theme_changed.connect(self._restyle_tray)

    def changeEvent(self, event: QEvent) -> None:
        """Intercept minimize events and hide the window to the system tray.

        Args:
            event: The change event delivered by Qt.
        """
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                # Hide to tray instead of showing a minimised taskbar entry
                self.hide()
        super().changeEvent(event)

    # ── Slots ──────────────────────────────────────────────────────────────────

    @Slot(str,int)
    def _on_file_received_metadata(self, filename: str, file_size: int) -> None:
        # Show the file-received toast when incoming metadata arrives.
        self._toast = FileReceivedToast(filename, file_size)
        self._toast.show_toast()

    @Slot(int)
    def _change_page(self, index: int) -> None:
        # Switch the stacked widget to the screen at the given index.
        self._stack.setCurrentIndex(index)

    @Slot()
    def _restore_window(self) -> None:
        # Bring the window back from the tray and give it focus.
        self.showNormal()
        self.activateWindow()
        self.raise_()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Restore the window on double-click; single-click opens the context menu natively.
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_window()

    @Slot()
    def _restyle_tray(self) -> None:
        # Reload the tray-menu QSS whenever the theme changes.
        self._tray_menu.setStyleSheet(
            utils.styles.load_stylesheet(
                Styles.TRAY_MENU,
                themed([Colors], [LightColors], theme_manager.is_dark),
            )
        )

    @Slot()
    def _on_file_receive_error(self, error: str) -> None:
        # Show the generic transfer-error dialog; error string is displayed inside it.
        TransferErrorDialog()

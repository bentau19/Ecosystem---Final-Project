from PySide6.QtCore import Slot, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMenu, QStackedWidget,
    QSystemTrayIcon, QWidget,
)

import utils.styles
from app.app_state import app_state
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

        self._navigation_manager: NavigationManager = navigation_manager
        self._screens: dict[Screen, QWidget]

        self._file_transfer_vm = app_state.file_transfer_viewmodel

        self._setup_ui()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────
    def _setup_ui(self) -> None:
        """Build the stacked widget, register both screens, and set up the tray."""
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
        """Wire the navigation managers navigate signal to the page-change slot."""
        self._navigation_manager.navigate.connect(self._change_page)
        self._file_transfer_vm.receive_error.connect(self._on_file_receive_error)
        self._file_transfer_vm.metadata_received.connect(self._on_file_received_metadata)

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
    def _on_file_received_metadata(self,filename: str, file_size: int) -> None:
        self._toast = FileReceivedToast(filename, file_size)
        self._toast.show_toast()

    @Slot(int)
    def _change_page(self, index: int) -> None:
        """Switch the stacked widget to the screen at the given index.

        Args:
            index: Zero-based index of the target screen in the stack,
                corresponding to the insertion order in :meth:`_setup_ui`.
        """
        self._stack.setCurrentIndex(index)

    @Slot()
    def _restore_window(self) -> None:
        """Show and bring the main window to the foreground."""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Restore the window on double-click of the tray icon.

        Args:
            reason: The activation reason provided by the tray icon event.
        """
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_window()

    @Slot()
    def _on_file_receive_error(self, error: str) -> None:
        TransferErrorDialog()

from pathlib import Path

from PySide6.QtCore import Slot, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QMainWindow, QMenu, QStackedWidget,
    QSystemTrayIcon, QWidget,
)

import utils.styles
from app.app_state import app_state
from app.theme_manager import theme_manager
from domain.dto.backup_file import BackupFileDTO
from domain.dto.backup_review_prompt import BackupReviewPromptDTO  # used in type hint for _on_backup_session_result
from domain.dto.file_receive_prompt import FileReceivePromptDTO
from domain.enums.screen import Screen
from resources.colors import Colors, LightColors
from resources.paths import Icons, Styles
from app.navigation_manager import navigation_manager, NavigationManager
from utils.styles import themed
from views.screens.dashboard import DashboardScreen
from views.screens.login import LoginScreen
from views.widgets.backup.backup_dest_picker_dialog import BackupDestPickerDialog
from views.widgets.backup.backup_progress_window import BackupProgressWindow
from views.widgets.backup.backup_review_dialog import BackupReviewDialog
from views.widgets.dialogs.file_handler import TransferErrorDialog
from views.widgets.toasts.file_received import FileReceivedToast
from viewmodels.backup import BackupViewModel
from viewmodels.file_transfer import FileTransferViewModel


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

        self._file_transfer_vm: FileTransferViewModel = app_state.file_transfer_viewmodel
        self._backup_vm: BackupViewModel = app_state.backup_viewmodel
        # Holds the BackupProgressWindow alive for the duration of a session.
        self._backup_progress_win: BackupProgressWindow | None = None
        # Holds the FileReceivedToast alive while it's on screen.
        self._toast: FileReceivedToast | None = None
        self._clipboard_service = app_state.clipboard_service

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
        # Tray icon visibility is managed reactively by showEvent/hideEvent.

    def _connect_signals(self) -> None:
        # Wire navigation, file-transfer, backup, theme, and clipboard signals to their slots.
        self._navigation_manager.navigate.connect(self._change_page)
        self._file_transfer_vm.receive_error.connect(self._on_file_receive_error)
        self._file_transfer_vm.send_error.connect(self._on_file_send_error)
        self._file_transfer_vm.metadata_received.connect(self._on_file_received_metadata)
        self._backup_vm.dest_dir_requested.connect(self._on_dest_dir_requested)
        self._backup_vm.backup_ready.connect(self._on_backup_ready)
        self._backup_vm.backup_session_result.connect(self._on_backup_session_result)
        self._backup_vm.device_ready_changed.connect(self._on_backup_device_ready_changed)
        app_state.device_viewmodel.connection_error.connect(self._on_connection_error)
        self._clipboard_service.clipboard_text_received.connect(self._on_clipboard_text_received)
        theme_manager.theme_changed.connect(self._restyle_tray)
        # PC → Android: delegate clipboard changes entirely to the service.
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

    def changeEvent(self, event: QEvent) -> None:
        """Intercept minimize events and hide the window to the system tray.

        Args:
            event: The change event delivered by Qt.
        """
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                # Hide to tray instead of showing a minimised taskbar entry.
                # hideEvent will fire automatically and show the tray icon.
                self.hide()
        super().changeEvent(event)

    def showEvent(self, event: QEvent) -> None:
        """Hide the tray icon while the window is visible.

        Args:
            event: The show event delivered by Qt.
        """
        super().showEvent(event)
        self._tray_icon.hide()

    def hideEvent(self, event: QEvent) -> None:
        """Show the tray icon whenever the window is hidden so the user can restore it.

        Args:
            event: The hide event delivered by Qt.
        """
        super().hideEvent(event)
        self._tray_icon.show()

    # ── Slots ──────────────────────────────────────────────────────────────────

    @Slot(object)
    def _on_file_received_metadata(self, dto: FileReceivePromptDTO) -> None:
        # Show the file-received toast when incoming metadata arrives.
        self._toast = FileReceivedToast(dto.filename, dto.size)
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

    @Slot(int, 'qint64', bool)
    def _on_dest_dir_requested(self, file_count: int, files_size: int,
                                storage_saver: bool) -> None:
        # Android sent a manifest — show the folder-picker dialog. Opens
        # BackupDestPickerDialog modally. On accept, unblocks the service with
        # the chosen path; on cancel, aborts the session.
        #
        # Restore the window first: a QDialog with a hidden parent will not
        # render on screen, leaving the backup service stuck waiting forever.
        if not self.isVisible():
            self._restore_window()
        dlg = BackupDestPickerDialog(file_count, files_size,
                                     storage_saver=storage_saver, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._backup_vm.confirm_dest_dir(dlg.selected_path)
        else:
            self._backup_vm.cancel_dest_selection()

    @Slot(int, 'qint64')
    def _on_backup_ready(self, file_count: int, total_bytes: int) -> None:
        # User confirmed a destination — open the backup progress window.
        # Creates a fresh BackupProgressWindow, wires it to the ViewModel, and
        # shows it as a separate top-level window. The reference is stored on
        # self so Qt does not garbage-collect it immediately.
        self._backup_progress_win = BackupProgressWindow(
            file_count=file_count,
            total_bytes=total_bytes,
        )
        self._backup_progress_win.connect_viewmodel(self._backup_vm)
        self._backup_progress_win.show()

    @Slot(list, str)
    def _on_backup_session_result(self, flagged: list[BackupReviewPromptDTO], dest_dir: str) -> None:
        # Fired after backup_complete. Close the progress window (safe — _backup_done
        # is already True) then show a review dialog for any ML-flagged files.
        #
        # Non-blocking design: the main window is NOT force-restored to the front.
        # Completion is communicated via a tray balloon so the user is informed
        # without interrupting whatever they are currently doing.
        if self._backup_progress_win is not None:
            self._backup_progress_win.close()
            self._backup_progress_win = None

        if flagged:
            # Stat only the handful of ML-flagged files — no directory scan needed.
            # prompt.cache_path is the final dest_dir path set by the service.
            files: list[BackupFileDTO] = []
            for prompt in flagged:
                try:
                    st = Path(prompt.cache_path).stat()
                    files.append(BackupFileDTO(
                        path=prompt.cache_path,
                        name=prompt.file_name,
                        size_bytes=st.st_size,
                        mtime=int(st.st_mtime * 1000),
                    ))
                except OSError:
                    pass  # file was already deleted (e.g. disk error) — skip it

            if files:
                dlg = BackupReviewDialog(files, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    decisions = dlg.get_decisions()
                    deleted_count = 0
                    for path, decision in decisions.items():
                        if decision == "delete":
                            Path(path).unlink(missing_ok=True)
                            deleted_count += 1

                    kept = len(files) - deleted_count
                    self._tray_icon.showMessage(
                        "Backup Review Complete",
                        f"{kept} file{'s' if kept != 1 else ''} kept"
                        f", {deleted_count} deleted"
                        f"\nFiles saved to: {dest_dir}",
                        QSystemTrayIcon.MessageIcon.Information,
                        6000,
                    )
                return

        # No flagged files — classify=False or every ML file passed automatically.
        self._tray_icon.showMessage(
            "Backup Complete",
            "All files have been saved successfully.",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    @Slot(bool)
    def _on_backup_device_ready_changed(self, ready: bool) -> None:
        """Force-close the backup progress window when the device disconnects mid-backup.

        The ViewModel has already cancelled the session (reset ``_is_active``)
        before emitting this signal, so the window can be torn down without a
        confirmation dialog via :meth:`~BackupProgressWindow.force_close`.
        """
        if not ready and self._backup_progress_win is not None:
            self._backup_progress_win.force_close()
            self._backup_progress_win = None

    @Slot(str)
    def _on_file_receive_error(self, error: str) -> None:
        # Show the generic transfer-error dialog; error string is displayed inside it.
        TransferErrorDialog()

    @Slot(str)
    def _on_file_send_error(self, error: str) -> None:
        # Mirror of _on_file_receive_error for the outbound direction.
        TransferErrorDialog()

    @Slot(str)
    def _on_connection_error(self, error: str) -> None:
        # Non-blocking tray notification — the listener retries automatically
        # so no dialog is needed; the user just needs to know something went wrong.
        self._tray_icon.showMessage(
            "Connection Error",
            f"Could not listen for connections: {error}\nRetrying…",
            QSystemTrayIcon.MessageIcon.Warning,
            4000,
        )

    @Slot(str)
    def _on_clipboard_text_received(self, text: str) -> None:
        # Always called on the main thread via Qt's queued connection — safe to touch QClipboard.
        # Hash management is handled inside ClipboardService._receive() before this signal
        # was emitted, so no logic needed here.
        QApplication.clipboard().setText(text)

    @Slot()
    def _on_clipboard_changed(self) -> None:
        # Thin relay — all sync logic (hash guard, send decision) lives in ClipboardService.
        self._clipboard_service.on_clipboard_changed(QApplication.clipboard().text())

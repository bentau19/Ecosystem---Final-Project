from pathlib import Path

from PySide6.QtCore import Slot, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QMainWindow, QMenu, QMessageBox, QStackedWidget,
    QSystemTrayIcon, QWidget,
)

import utils.styles
from app.app_state import app_state
from app.theme_manager import theme_manager
from domain.dto.backup_file import BackupFileDTO
from domain.dto.backup_review_prompt import BackupReviewPromptDTO
from domain.dto.file_receive_prompt import FileReceivePromptDTO
from domain.enums.screen import Screen
from resources.colors import Colors, LightColors
from resources.paths import Icons, Styles
from app.navigation_manager import navigation_manager, NavigationManager
from utils.file_type import IMAGE_EXTS, file_ext
from utils.styles import themed
from views.screens.dashboard import DashboardScreen
from views.screens.login import LoginScreen
from views.widgets.backup.backup_classification_review_dialog import BackupClassificationReviewDialog
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
        # Set to True when the user clicks "Keep All Files" in a review dialog,
        # so that subsequent review prompts in the same session are auto-kept.
        # Reset to False each time a new backup session manifest arrives.
        self._keep_all_reviews: bool = False

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
        # Wire navigation, file-transfer, backup, and theme signals to their slots.
        self._navigation_manager.navigate.connect(self._change_page)
        self._file_transfer_vm.receive_error.connect(self._on_file_receive_error)
        self._file_transfer_vm.metadata_received.connect(self._on_file_received_metadata)
        self._backup_vm.dest_dir_requested.connect(self._on_dest_dir_requested)
        self._backup_vm.backup_ready.connect(self._on_backup_ready)
        self._backup_vm.review_requested.connect(self._on_review_requested)
        self._backup_vm.backup_session_result.connect(self._on_backup_session_result)
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

    @Slot(int, 'qint64')
    def _on_dest_dir_requested(self, file_count: int, files_size: int) -> None:
        # Android sent a manifest — show the folder-picker dialog. Opens
        # BackupDestPickerDialog modally. On accept, unblocks the service with
        # the chosen path; on cancel, aborts the session.
        # Reset the "keep all" flag so each new session starts fresh.
        self._keep_all_reviews = False
        dlg = BackupDestPickerDialog(file_count, files_size, parent=self)
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

    @Slot(object)
    def _on_review_requested(self, prompt: BackupReviewPromptDTO) -> None:
        # The classifier flagged a file as ambiguous — ask the user to decide.
        # Opens BackupClassificationReviewDialog modally. The user's choice is
        # reported back to the service via BackupViewModel.resolve_review,
        # which unblocks the slot's receiver thread.
        #
        # If the user previously clicked "Keep All Files", skip the dialog and
        # auto-keep every subsequent file in this session without interrupting.
        #
        # The progress window may be minimized to the system tray when this
        # fires, so this dialog is raised on top of the main window to ensure
        # it's visible.
        if self._keep_all_reviews:
            self._backup_vm.resolve_review(prompt.channel, True)
            return

        self.showNormal()
        self.activateWindow()
        self.raise_()

        dlg = BackupClassificationReviewDialog(prompt, parent=self)
        result = dlg.exec()

        if result == BackupClassificationReviewDialog.KEEP_ALL_CODE:
            # Keep this file and suppress all further review dialogs this session.
            self._keep_all_reviews = True

        # Any result that is not Rejected counts as "keep".
        self._backup_vm.resolve_review(
            prompt.channel,
            result != QDialog.DialogCode.Rejected,
        )

    @Slot(bool, str)
    def _on_backup_session_result(self, classify: bool, dest_dir: str) -> None:
        # Fired after backup_complete. Close the progress window (safe — _backup_done
        # is already True) then branch on whether ML classification was enabled.
        if self._backup_progress_win is not None:
            self._backup_progress_win.close()
            self._backup_progress_win = None

        # Ensure the main window is visible in case it was hidden to the tray.
        self.showNormal()
        self.activateWindow()
        self.raise_()

        if classify:
            # Build a list of every image file that was saved to dest_dir.
            # rglob handles Android rel_path subdirectories (e.g. DCIM/Camera/).
            dest = Path(dest_dir)
            files: list[BackupFileDTO] = []
            if dest.exists():
                for f in sorted(dest.rglob("*")):
                    if f.is_file() and file_ext(f.name) in IMAGE_EXTS:
                        try:
                            st = f.stat()
                            files.append(BackupFileDTO(
                                path=str(f),
                                name=f.name,
                                size_bytes=st.st_size,
                                mtime=int(st.st_mtime * 1000),
                            ))
                        except OSError:
                            pass

            if files:
                # Let the user keep or delete each image; apply decisions on Accept.
                dlg = BackupReviewDialog(files, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    decisions = dlg.get_decisions()
                    deleted_count = 0
                    kept_count = 0

                    for path, decision in decisions.items():
                        if decision == "delete":
                            Path(path).unlink(missing_ok=True)
                            deleted_count += 1
                        elif decision == "keep":
                            # Files are already in dest_dir — the backup service
                            # wrote them there before the review ran.  No copy
                            # is required; count for the summary only.
                            kept_count += 1

                    parts: list[str] = []
                    if kept_count:
                        parts.append(f"{kept_count} file{'s' if kept_count != 1 else ''} kept")
                    if deleted_count:
                        parts.append(f"{deleted_count} file{'s' if deleted_count != 1 else ''} deleted")
                    summary = ", ".join(parts) if parts else "No changes made."

                    QMessageBox.information(
                        self,
                        "Backup Review Complete",
                        f"Decisions applied.\n\n{summary}\n\nFiles are saved to:\n{dest_dir}",
                    )
                return

        # classify=False, or classify=True but no images were found
        QMessageBox.information(
            self,
            "Backup Complete",
            "Backup completed successfully!\nAll files have been saved.",
        )

    @Slot()
    def _on_file_receive_error(self, error: str) -> None:
        # Show the generic transfer-error dialog; error string is displayed inside it.
        TransferErrorDialog()

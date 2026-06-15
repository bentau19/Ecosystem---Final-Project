from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Final

from PySide6.QtCore import Qt, QEvent, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QLabel,
    QListView, QMainWindow, QMenu, QMessageBox, QPushButton,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from app.theme_manager import theme_manager
from domain.enums.backup_status import BackupStatus
from resources.colors import BackupProgressColors, LightBackupProgressColors, Palette
from resources.paths import BackupStyles, Icons
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from views.widgets.backup.backup_progress_delegate import (
    BackupProgressDelegate, fmt_elapsed, fmt_eta,
)
from views.widgets.backup.backup_progress_model import BackupProgressModel, make_colors
from views.widgets.bar import Bar

if TYPE_CHECKING:
    from viewmodels.backup import BackupViewModel

# ── Layout constants ───────────────────────────────────────────────────────────
_WINDOW_MIN_WIDTH: Final[int] = 620
_WINDOW_MIN_HEIGHT: Final[int] = 500
_WINDOW_MAX_HEIGHT: Final[int] = 820
_HEADER_ICON_SIZE: Final[int] = 40
_BUTTON_HEIGHT: Final[int] = 36
_LIST_SPACING: Final[int] = 4


class BackupProgressWindow(QMainWindow):
    """Standalone window showing per-file backup progress.

    The scroll list is backed by :class:`~backup_progress_model.BackupProgressModel` +
    :class:`~backup_progress_delegate.BackupProgressDelegate` — only visible rows
    are rendered, so the window stays responsive regardless of file count.

    Drive the window by calling :meth:`connect_viewmodel` after construction::

        win = BackupProgressWindow(file_count, total_bytes)
        win.connect_viewmodel(app_state.backup_viewmodel)
        win.show()

    Signals:
        pause_requested:  Emitted when the user clicks **Pause All**.
        resume_requested: Emitted when the user clicks **Resume**.
        cancel_requested: Emitted after the user confirms cancellation.
    """

    pause_requested: Signal = Signal()
    resume_requested: Signal = Signal()
    cancel_requested: Signal = Signal()

    def __init__(
            self,
            file_count: int,
            total_bytes: int,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._total_files: int = file_count
        self._paused: bool = False
        self._backup_done: bool = False
        self._cancelling: bool = False
        self._closing: bool = False  # True once window is being permanently closed (not minimised)
        self._auto_scroll: bool = True
        self._started_at: datetime = datetime.now()

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── ViewModel wiring ──────────────────────────────────────────────────────

    def force_close(self) -> None:
        """Close the window immediately without the cancel-confirmation dialog.

        Used when the device disconnects mid-backup — the phone is already gone
        so there is nothing to cancel on the Android side and no user prompt is
        needed.  Sets :attr:`_cancelling` so :meth:`closeEvent` bypasses its
        ``QMessageBox.question`` guard, then hides the tray icon and closes.
        """
        self._cancelling = True
        self._tray_icon.hide()
        self._closing = True
        self.close()

    def connect_viewmodel(self, vm: BackupViewModel) -> None:
        """Wire this window to *vm*."""
        vm.file_registered.connect(self._on_file_registered)
        vm.file_progress_updated.connect(self._on_file_progress)
        vm.file_status_changed.connect(self._on_file_status_changed)
        vm.file_saved_at.connect(self._on_file_saved_at)
        vm.overall_updated.connect(self._on_overall_updated)
        vm.backup_complete.connect(self._on_backup_complete)
        vm.backup_error.connect(self._on_backup_error)
        vm.pause_state_changed.connect(self._apply_pause_state)

        self.pause_requested.connect(vm.pause)
        self.resume_requested.connect(vm.resume)
        self.cancel_requested.connect(vm.cancel)

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("BackupProgressWindow")
        self.setWindowTitle("SyncDose — Backup Progress")
        self.setMinimumWidth(_WINDOW_MIN_WIDTH)
        self.setMinimumHeight(_WINDOW_MIN_HEIGHT)
        self.setMaximumHeight(_WINDOW_MAX_HEIGHT)
        self._create_widgets()
        self._setup_layout()
        self._setup_tray()

    def _create_widgets(self) -> None:
        # _model must be created first; the other helpers reference it.
        self._list_view: QListView = self._create_list_view()
        self._header: QWidget = self._create_header()
        self._overall_section: QWidget = self._create_overall_section()
        self._summary_label: QLabel = self._create_summary_label()
        self._auto_scroll_btn: QPushButton = self._create_auto_scroll_button()
        self._pause_btn: QPushButton = self._create_pause_button()
        self._cancel_btn: QPushButton = self._create_cancel_button()

    # ── Header ────────────────────────────────────────────────────────────────

    def _create_header(self) -> QWidget:
        container = QWidget()
        container.setObjectName("BPWHeader")

        icon = QLabel("☁")
        icon.setObjectName("HeaderIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(_HEADER_ICON_SIZE, _HEADER_ICON_SIZE)

        title = QLabel("Backing Up Files")
        title.setObjectName("HeaderTitle")

        n = self._total_files
        subtitle = QLabel(
            f"{n} file{'s' if n != 1 else ''}  ·  "
            f"Started {self._started_at.strftime('%H:%M')}"
        )
        subtitle.setObjectName("HeaderSubtitle")

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.addWidget(title)
        text_col.addWidget(subtitle)

        row = QHBoxLayout(container)
        row.setContentsMargins(Spacing.XXL, Spacing.LG, Spacing.XXL, Spacing.LG)
        row.setSpacing(Spacing.MD)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addLayout(text_col, 1)
        return container

    # ── Overall progress section ───────────────────────────────────────────────

    def _create_overall_section(self) -> QWidget:
        container = QWidget()
        container.setObjectName("OverallSection")

        self._overall_bar = Bar(0, QColor(Palette.CYAN_400), QColor(Palette.TEAL_400))
        self._overall_bar.setFixedHeight(10)

        self._overall_pct = QLabel("0%")
        self._overall_pct.setObjectName("OverallPercent")
        self._overall_pct.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._overall_pct.setFixedWidth(52)

        self._overall_stats = QLabel(self._build_stats_text())
        self._overall_stats.setObjectName("OverallStats")

        self._overall_eta_label = QLabel("")
        self._overall_eta_label.setObjectName("OverallEta")
        self._overall_eta_label.setVisible(False)

        bar_row = QHBoxLayout()
        bar_row.setContentsMargins(0, 0, 0, 0)
        bar_row.setSpacing(Spacing.SM)
        bar_row.addWidget(self._overall_bar, 1, Qt.AlignmentFlag.AlignVCenter)
        bar_row.addWidget(self._overall_pct, 0, Qt.AlignmentFlag.AlignVCenter)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        inner.setSpacing(Spacing.XS)
        inner.addLayout(bar_row)
        inner.addWidget(self._overall_stats)
        inner.addWidget(self._overall_eta_label)
        return container

    # ── File list ─────────────────────────────────────────────────────────────

    def _create_list_view(self) -> QListView:
        self._model = BackupProgressModel(parent=self)
        self._delegate = BackupProgressDelegate(make_colors(theme_manager.is_dark), parent=self)

        lv = QListView()
        lv.setObjectName("FileListView")
        lv.setModel(self._model)
        lv.setItemDelegate(self._delegate)
        lv.setUniformItemSizes(True)
        lv.setSpacing(_LIST_SPACING)
        lv.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        lv.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lv.setFrameShape(QFrame.Shape.NoFrame)
        return lv

    # ── Footer ────────────────────────────────────────────────────────────────

    def _create_summary_label(self) -> QLabel:
        lbl = QLabel(self._build_summary_text())
        lbl.setObjectName("FooterSummary")
        return lbl

    @staticmethod
    def _create_auto_scroll_button() -> QPushButton:
        btn = QPushButton("⤓  Auto-scroll")
        btn.setObjectName("AutoScrollButton")
        btn.setFixedHeight(_BUTTON_HEIGHT)
        btn.setMinimumWidth(118)
        btn.setCheckable(True)
        btn.setChecked(True)  # enabled by default
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    @staticmethod
    def _create_pause_button() -> QPushButton:
        btn = QPushButton("⏸  Pause All")
        btn.setObjectName("PauseButton")
        btn.setFixedHeight(_BUTTON_HEIGHT)
        btn.setMinimumWidth(118)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    @staticmethod
    def _create_cancel_button() -> QPushButton:
        btn = QPushButton("✗  Cancel All")
        btn.setObjectName("CancelAllButton")
        btn.setFixedHeight(_BUTTON_HEIGHT)
        btn.setMinimumWidth(118)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    # ── Root layout ───────────────────────────────────────────────────────────

    def _setup_layout(self) -> None:
        central = QWidget()
        central.setObjectName("BPWContent")

        root = QVBoxLayout(central)
        root.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        root.setSpacing(Spacing.NONE)

        overall_wrapper = QHBoxLayout()
        overall_wrapper.setContentsMargins(Spacing.XXL, Spacing.MD, Spacing.XXL, Spacing.MD)
        overall_wrapper.addWidget(self._overall_section)

        root.addWidget(self._header)
        root.addWidget(self._make_divider())
        root.addLayout(overall_wrapper)
        root.addWidget(self._make_divider())
        root.addWidget(self._list_view, 1)
        root.addWidget(self._make_divider())
        root.addLayout(self._make_footer())

        self.setCentralWidget(central)

    @staticmethod
    def _make_divider() -> QFrame:
        line = QFrame()
        line.setObjectName("BPWDivider")
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setFixedHeight(1)
        return line

    def _make_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(Spacing.XXL, Spacing.MD, Spacing.XXL, Spacing.LG)
        footer.setSpacing(Spacing.SM)
        footer.addWidget(self._summary_label, 1)
        footer.addWidget(self._auto_scroll_btn)
        footer.addWidget(self._pause_btn)
        footer.addWidget(self._cancel_btn)
        return footer

    # ── System tray ───────────────────────────────────────────────────────────

    def _setup_tray(self) -> None:
        # Use a dedicated cloud-upload icon so the backup tray entry is visually
        # distinct from the main SyncDose tray icon (Icons.LOGO).
        self._tray_icon = QSystemTrayIcon(QIcon(Icons.BACKUP_PROGRESS), parent=self)
        self._tray_icon.setToolTip("SyncDose — Backup  0% completed")

        self._tray_menu = QMenu()
        open_action: QAction = self._tray_menu.addAction("Open Backup Progress")
        self._tray_menu.addSeparator()
        self._tray_pause_act: QAction = self._tray_menu.addAction("⏸  Pause All")
        cancel_action: QAction = self._tray_menu.addAction("✗  Cancel Backup")

        open_action.triggered.connect(self._restore_window)
        self._tray_pause_act.triggered.connect(self._on_pause_clicked)
        cancel_action.triggered.connect(self._on_cancel_requested)

        self._tray_icon.setContextMenu(self._tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        # Tray visibility is managed reactively by showEvent/hideEvent.

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        qss = load_stylesheet(
            BackupStyles.PROGRESS,
            themed([BackupProgressColors], [LightBackupProgressColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)
        self._delegate.update_colors(make_colors(theme_manager.is_dark))
        self._list_view.viewport().update()

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._auto_scroll_btn.toggled.connect(self._on_auto_scroll_toggled)
        self._pause_btn.clicked.connect(self._on_pause_clicked)
        self._cancel_btn.clicked.connect(self._on_cancel_requested)
        theme_manager.theme_changed.connect(self._apply_style)

    # ── ViewModel slots ───────────────────────────────────────────────────────

    @Slot(str, 'qint64')
    def _on_file_registered(self, rel_path: str, size_bytes: int) -> None:
        self._model.register_file(rel_path, size_bytes)
        self._refresh_summary()
        if self._auto_scroll:
            self._list_view.scrollToBottom()

    @Slot(str, 'qint64', float)
    def _on_file_progress(self, path: str, bytes_done: int, speed_bps: float) -> None:
        self._model.update_progress(path, bytes_done, speed_bps)

    @Slot(str, object)
    def _on_file_status_changed(self, path: str, status: BackupStatus) -> None:
        self._model.update_status(path, status)
        self._refresh_summary()
        self._refresh_tray_tooltip()

    @Slot(str, str)
    def _on_file_saved_at(self, file_name: str, abs_path: str) -> None:
        """Load a thumbnail now that the file is confirmed saved to disk."""
        self._model.trigger_thumb(file_name, abs_path)

    @Slot('qint64', 'qint64', float)
    def _on_overall_updated(self, total_bytes: int, done_bytes: int, eta_secs: float) -> None:
        if total_bytes > 0:
            pct = int(done_bytes / total_bytes * 100)
            self._overall_bar.set_percent(pct)
            self._overall_pct.setText(f"{pct}%")
        self._overall_stats.setText(self._build_stats_text())

        elapsed_secs = int((datetime.now() - self._started_at).total_seconds())
        elapsed_str = fmt_elapsed(elapsed_secs)
        if eta_secs >= 0:
            self._overall_eta_label.setText(f"{fmt_eta(eta_secs)}  ·  {elapsed_str}")
            self._overall_eta_label.setVisible(True)
        elif elapsed_secs > 0:
            self._overall_eta_label.setText(elapsed_str)
            self._overall_eta_label.setVisible(True)

        self._refresh_tray_tooltip()

    @Slot()
    def _on_backup_complete(self) -> None:
        self._backup_done = True
        self._overall_bar.set_percent(100)
        self._overall_pct.setText("100%")
        self._overall_stats.setText("Backup complete  ✓")
        elapsed_secs = int((datetime.now() - self._started_at).total_seconds())
        self._overall_eta_label.setText(
            f"Finished in {fmt_elapsed(elapsed_secs).replace(' elapsed', '')}"
        )
        self._overall_eta_label.setVisible(True)
        self._pause_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._tray_icon.setToolTip("SyncDose — Backup completed  ✓")

    @Slot(str)
    def _on_backup_error(self, error: str) -> None:
        self._overall_stats.setText(f"Error: {error}")

    # ── User-action slots ─────────────────────────────────────────────────────

    @Slot()
    def _on_pause_clicked(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self._pause_btn.setText("▶  Resume")
            self._tray_pause_act.setText("▶  Resume")
            self.pause_requested.emit()
        else:
            self._pause_btn.setText("⏸  Pause All")
            self._tray_pause_act.setText("⏸  Pause All")
            self.resume_requested.emit()

    @Slot(bool)
    def _apply_pause_state(self, is_paused: bool) -> None:
        if self._paused == is_paused:
            return
        self._paused = is_paused
        label = "▶  Resume" if is_paused else "⏸  Pause All"
        self._pause_btn.setText(label)
        self._tray_pause_act.setText(label)
        self._refresh_tray_tooltip()  # update immediately, don't wait for next progress tick

    @Slot(bool)
    def _on_auto_scroll_toggled(self, checked: bool) -> None:
        self._auto_scroll = checked
        if checked:
            self._list_view.scrollToBottom()

    @Slot()
    def _on_cancel_requested(self) -> None:
        reply = QMessageBox.question(
            self,
            "Cancel Backup",
            "Are you sure you want to cancel the backup?\n"
            "Files not yet synced will not be backed up.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._cancelling = True
            self.cancel_requested.emit()
            self._tray_icon.hide()
            self.close()

    @Slot()
    def _restore_window(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_window()

    # ── Qt event overrides ────────────────────────────────────────────────────

    def showEvent(self, event: QEvent) -> None:
        """Hide the tray icon while the window is visible."""
        super().showEvent(event)
        self._tray_icon.hide()

    def hideEvent(self, event: QEvent) -> None:
        """Show the tray icon when the window is hidden to the tray (minimised).

        Suppressed when the window is closing permanently — the tray icon
        should disappear entirely, not reappear as an orphan entry.
        """
        super().hideEvent(event)
        if not self._closing:
            self._tray_icon.show()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self.hide()
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._cancelling or self._backup_done:
            self._tray_icon.hide()
            self._closing = True
            event.accept()
            return

        reply = QMessageBox.question(
            self,
            "Cancel Backup",
            "Closing this window will cancel the backup.\n"
            "Files not yet synced will not be backed up. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._cancelling = True
            self.cancel_requested.emit()
            self._tray_icon.hide()
            self._closing = True
            event.accept()
        else:
            event.ignore()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _refresh_summary(self) -> None:
        self._summary_label.setText(self._build_summary_text())
        self._overall_stats.setText(self._build_stats_text())  # keep upper count in sync

    def _refresh_tray_tooltip(self) -> None:
        pct = self._overall_bar.percent
        if self._paused:
            self._tray_icon.setToolTip(f"SyncDose — Backup paused  ({pct}% completed)")
        else:
            self._tray_icon.setToolTip(f"SyncDose — Backup  {pct}% completed")

    def _build_stats_text(self) -> str:
        counts = self._model.summary_counts()
        # All terminal states count toward "X of N" so the counter reaches N
        # even when some files fail.  The footer summary already shows the
        # per-status breakdown (done / syncing / queued / failed) separately.
        complete = (
            counts.get(BackupStatus.DONE, 0)
            + counts.get(BackupStatus.SKIPPED, 0)
            + counts.get(BackupStatus.FAILED, 0)
        )
        n = self._total_files
        return f"{complete} of {n} file{'s' if n != 1 else ''} complete"

    def _build_summary_text(self) -> str:
        counts = self._model.summary_counts()
        # Mirror _build_stats_text: DONE + SKIPPED both count as "done"
        done = counts.get(BackupStatus.DONE, 0) + counts.get(BackupStatus.SKIPPED, 0)
        parts: list[str] = []
        if done:                                parts.append(f"{done} done")
        if counts.get(BackupStatus.ACTIVE, 0):  parts.append(f"{counts[BackupStatus.ACTIVE]} syncing")
        if counts.get(BackupStatus.QUEUED, 0):  parts.append(f"{counts[BackupStatus.QUEUED]} queued")
        if counts.get(BackupStatus.FAILED, 0):  parts.append(f"{counts[BackupStatus.FAILED]} failed")
        return "  ·  ".join(parts) if parts else "No files"

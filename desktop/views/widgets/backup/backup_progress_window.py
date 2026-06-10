from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from PySide6.QtCore import Qt, QEvent, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QMessageBox, QPushButton, QScrollArea,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from app.theme_manager import theme_manager
from domain.dto.backup_file import BackupFileDTO
from domain.enums.backup_status import BackupStatus
from resources.colors import (
    BackupProgressColors, LightBackupProgressColors,
    Palette,
)
from resources.paths import BackupStyles, Icons
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from utils.file_type import IMAGE_EXTS, file_emoji, file_ext, fmt_size
from views.widgets.backup.helpers import load_thumb
from views.widgets.bar import Bar

if TYPE_CHECKING:
    from viewmodels.backup import BackupViewModel

# ── Layout constants ───────────────────────────────────────────────────────────
_WINDOW_MIN_WIDTH: Final[int] = 620
_WINDOW_MIN_HEIGHT: Final[int] = 500
_WINDOW_MAX_HEIGHT: Final[int] = 820
_HEADER_ICON_SIZE: Final[int] = 40
_ROW_ICON_SIZE: Final[int] = 44
_BUTTON_HEIGHT: Final[int] = 36
_STATUS_BADGE_W: Final[int] = 90


# ── Speed / ETA formatter (progress-window only) ───────────────────────────────

def _fmt_speed_eta(speed_bps: float, remaining_bytes: int) -> str:
    # Format a speed + ETA string, e.g. "2.3 MB/s  ·  12s left".
    if speed_bps <= 0:
        return ""
    speed_str = fmt_size(int(speed_bps)) + "/s"
    secs = remaining_bytes / speed_bps
    if secs < 60:
        eta = f"{int(secs)}s left"
    elif secs < 3600:
        eta = f"{int(secs / 60)}m left"
    else:
        eta = f"{secs / 3600:.1f}h left"
    return f"{speed_str}  ·  {eta}"


def _fmt_elapsed(secs: int) -> str:
    # Format elapsed seconds, e.g. "1m 23s elapsed".
    if secs < 60:
        return f"{secs}s elapsed"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s elapsed"
    return f"{secs // 3600}h {(secs % 3600) // 60}m elapsed"


def _fmt_eta(secs: float) -> str:
    # Format estimated time remaining, e.g. "~45s left".
    s = int(secs)
    if s < 60:
        return f"~{s}s left"
    if s < 3600:
        return f"~{s // 60}m left"
    return f"~{secs / 3600:.1f}h left"


def _badge_text(status: BackupStatus) -> str:
    # Return the short display string for a status badge.
    return {
        BackupStatus.QUEUED: "Queued",
        BackupStatus.ACTIVE: "● Syncing",
        BackupStatus.DONE: "✓  Done",
        BackupStatus.FAILED: "✗  Failed",
    }[status]


# ── File row widget ────────────────────────────────────────────────────────────

class _BackupFileRow(QFrame):
    """Single file entry in the backup progress list.

    Displays a file-type icon (thumbnail for images, emoji for everything else),
    filename, size, an inline :class:`~views.widgets.bar.Bar` progress bar
    (visible only when *active*), speed + ETA, and a status badge.

    The ``status`` dynamic property drives all QSS colour-state selectors.
    Call :meth:`set_status` and :meth:`update_progress` to refresh the row.
    """

    def __init__(self, item: BackupFileDTO, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: str = item.path
        self._name: str = item.name
        self._size_bytes: int = item.size_bytes
        self._bytes_done: int = 0
        self._status: BackupStatus = BackupStatus.QUEUED
        self._setup_ui()

    # ── Public API ────────────────────────────────────────────────────────────

    def update_progress(self, bytes_done: int, speed_bps: float) -> None:
        """Refresh the inline bar fill and speed / ETA label.

        Args:
            bytes_done: Number of bytes transferred so far.
            speed_bps: Current transfer speed in bytes per second.
        """
        self._bytes_done = bytes_done
        pct = int(bytes_done / self._size_bytes * 100) if self._size_bytes else 0
        self._row_bar.set_percent(pct)
        remaining = max(0, self._size_bytes - bytes_done)
        self._speed_label.setText(_fmt_speed_eta(speed_bps, remaining))

    def set_status(self, status: BackupStatus) -> None:
        """Transition the row to *status*, updating QSS state and visibility.

        Args:
            status: The new :class:`BackupStatus` for this row.
        """
        self._status = status
        is_active = status == BackupStatus.ACTIVE
        self._row_bar.setVisible(is_active)
        self._speed_label.setVisible(is_active)
        self._status_badge.setText(_badge_text(status))

        # Flip the dynamic property on both the frame and the badge so their
        # QSS [status=...] attribute selectors pick up the new value.
        for widget in (self, self._status_badge):
            widget.setProperty("status", status.value)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("BackupProgressRow")
        self.setProperty("status", self._status.value)
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        self._icon_label: QLabel = self._create_icon()
        self._name_label: QLabel = self._create_name_label()
        self._size_label: QLabel = self._create_size_label()
        self._row_bar: Bar = self._create_row_bar()
        self._speed_label: QLabel = self._create_speed_label()
        self._status_badge: QLabel = self._create_status_badge()

    def _create_icon(self) -> QLabel:
        # Return a thumbnail for image files, or an emoji label for all others.
        lbl = QLabel()
        lbl.setObjectName("FileTypeIcon")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedSize(_ROW_ICON_SIZE, _ROW_ICON_SIZE)

        if file_ext(self._name) in IMAGE_EXTS:
            pixmap = load_thumb(self._path, _ROW_ICON_SIZE)
            if pixmap is not None:
                lbl.setPixmap(pixmap)
                return lbl

        lbl.setText(file_emoji(self._name))
        return lbl

    def _create_name_label(self) -> QLabel:
        lbl = QLabel(self._name)
        lbl.setObjectName("RowFileName")
        lbl.setToolTip(self._path)  # full path visible on hover
        return lbl

    def _create_size_label(self) -> QLabel:
        lbl = QLabel(fmt_size(self._size_bytes))
        lbl.setObjectName("RowFileSize")
        return lbl

    def _create_row_bar(self) -> Bar:
        # Inline gradient progress bar — hidden until status → active.
        bar = Bar(0, QColor(Palette.CYAN_400), QColor(Palette.TEAL_400))
        bar.setVisible(False)
        return bar

    def _create_speed_label(self) -> QLabel:
        lbl = QLabel("")
        lbl.setObjectName("RowSpeed")
        lbl.setVisible(False)
        return lbl

    def _create_status_badge(self) -> QLabel:
        lbl = QLabel(_badge_text(self._status))
        lbl.setObjectName("StatusBadge")
        lbl.setProperty("status", self._status.value)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedWidth(_STATUS_BADGE_W)
        return lbl

    def _setup_layout(self) -> None:
        # Top line: filename (expanding) + size (right-aligned)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(Spacing.SM)
        top_row.addWidget(self._name_label, 1)
        top_row.addWidget(self._size_label)

        # Info column: name/size → bar → speed
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(Spacing.XS)
        info_col.addLayout(top_row)
        info_col.addWidget(self._row_bar)
        info_col.addWidget(self._speed_label)

        # Root row: icon | info_col (stretch) | badge
        root = QHBoxLayout(self)
        root.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        root.setSpacing(Spacing.MD)
        root.addWidget(self._icon_label, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(info_col, 1)
        root.addWidget(self._status_badge, 0, Qt.AlignmentFlag.AlignVCenter)


# ── Main window ────────────────────────────────────────────────────────────────

class BackupProgressWindow(QMainWindow):
    """Standalone window showing per-file backup progress.

    Opens alongside the main SyncDose dashboard (same process, separate window).
    Minimising hides it to a **dedicated** :class:`~PySide6.QtWidgets.QSystemTrayIcon`;
    double-clicking the tray icon restores the window.  Closing the window
    prompts for cancellation confirmation.

    The widget is **purely presentational** — it is driven entirely by a
    :class:`~viewmodels.backup.BackupViewModel` connected via
    :meth:`connect_viewmodel`.

    Drive the window by calling :meth:`connect_viewmodel` after construction::

        win = BackupProgressWindow(files)
        win.connect_viewmodel(app_state.backup_viewmodel)
        win.show()

    The three user-action signals are wired to the ViewModel automatically by
    :meth:`connect_viewmodel` — callers do not need to connect them manually.

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
        self._rows: dict[str, _BackupFileRow] = {}
        # Lightweight status map kept in the view for footer summary text only.
        # Populated lazily as file_registered signals arrive from the ViewModel.
        self._statuses: dict[str, BackupStatus] = {}
        self._total_files: int = file_count
        self._paused: bool = False
        self._backup_done: bool = False  # skips cancel-confirm on close
        self._cancelling: bool = False  # prevents double close-event dialog
        self._started_at: datetime = datetime.now()

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── ViewModel wiring ──────────────────────────────────────────────────────

    def connect_viewmodel(self, vm: BackupViewModel) -> None:
        """Wire this window to *vm*.

        All ViewModel → View signal connections are established here, and the
        three user-action signals (pause / resume / cancel) are forwarded to
        the corresponding ViewModel methods.

        Args:
            vm: The :class:`~viewmodels.backup.BackupViewModel` driving this session.
        """
        vm.file_registered.connect(self._on_file_registered)
        vm.file_progress_updated.connect(self._on_file_progress)
        vm.file_status_changed.connect(self._on_file_status_changed)
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
        self._header: QWidget = self._create_header()
        self._overall_section: QWidget = self._create_overall_section()
        self._scroll_area: QScrollArea = self._create_scroll_area()
        self._summary_label: QLabel = self._create_summary_label()
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
        # Elevated card showing the overall progress bar, percentage and stats.
        container = QWidget()
        container.setObjectName("OverallSection")

        self._overall_bar: Bar = Bar(
            0,
            QColor(Palette.CYAN_400),
            QColor(Palette.TEAL_400),
        )
        self._overall_bar.setFixedHeight(10)

        self._overall_pct: QLabel = QLabel("0%")
        self._overall_pct.setObjectName("OverallPercent")
        self._overall_pct.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._overall_pct.setFixedWidth(52)

        self._overall_stats: QLabel = QLabel(self._build_stats_text())
        self._overall_stats.setObjectName("OverallStats")

        self._overall_eta_label: QLabel = QLabel("")
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

    # ── Scroll area ───────────────────────────────────────────────────────────

    def _create_scroll_area(self) -> QScrollArea:
        # Keep refs so _on_file_registered can insert rows into the live layout.
        self._scroll_content: QWidget = QWidget()
        self._scroll_content.setObjectName("FileScrollContent")

        self._scroll_layout: QVBoxLayout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        self._scroll_layout.setSpacing(Spacing.SM)
        self._scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # Rows are added lazily via _on_file_registered as slot headers arrive.

        scroll = QScrollArea()
        scroll.setObjectName("FileScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(self._scroll_content)
        return scroll

    # ── Footer ────────────────────────────────────────────────────────────────

    def _create_summary_label(self) -> QLabel:
        lbl = QLabel(self._build_summary_text())
        lbl.setObjectName("FooterSummary")
        return lbl

    def _create_pause_button(self) -> QPushButton:
        btn = QPushButton("⏸  Pause All")
        btn.setObjectName("PauseButton")
        btn.setFixedHeight(_BUTTON_HEIGHT)
        btn.setMinimumWidth(118)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _create_cancel_button(self) -> QPushButton:
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

        # Overall section has horizontal outer padding to sit inset from the edges
        overall_wrapper = QHBoxLayout()
        overall_wrapper.setContentsMargins(Spacing.XXL, Spacing.MD, Spacing.XXL, Spacing.MD)
        overall_wrapper.addWidget(self._overall_section)

        root.addWidget(self._header)
        root.addWidget(self._make_divider())
        root.addLayout(overall_wrapper)
        root.addWidget(self._make_divider())
        root.addWidget(self._scroll_area, 1)
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
        footer.addWidget(self._pause_btn)
        footer.addWidget(self._cancel_btn)
        return footer

    # ── System tray ───────────────────────────────────────────────────────────

    def _setup_tray(self) -> None:
        # Create the dedicated system-tray icon with a backup context menu.
        self._tray_icon: QSystemTrayIcon = QSystemTrayIcon(QIcon(Icons.LOGO), parent=self)
        self._tray_icon.setToolTip("SyncDose — Backup in progress…")

        self._tray_menu: QMenu = QMenu()
        open_action: QAction = self._tray_menu.addAction("Open Backup Progress")
        self._tray_menu.addSeparator()
        self._tray_pause_act: QAction = self._tray_menu.addAction("⏸  Pause All")
        cancel_action: QAction = self._tray_menu.addAction("✗  Cancel Backup")

        open_action.triggered.connect(self._restore_window)
        self._tray_pause_act.triggered.connect(self._on_pause_clicked)
        cancel_action.triggered.connect(self._on_cancel_requested)

        self._tray_icon.setContextMenu(self._tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        qss = load_stylesheet(
            BackupStyles.PROGRESS,
            themed([BackupProgressColors], [LightBackupProgressColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._pause_btn.clicked.connect(self._on_pause_clicked)
        self._cancel_btn.clicked.connect(self._on_cancel_requested)
        theme_manager.theme_changed.connect(self._apply_style)

    # ── ViewModel slots ───────────────────────────────────────────────────────

    @Slot(str, 'qint64')
    def _on_file_registered(self, rel_path: str, size_bytes: int) -> None:
        # Lazily create and insert a progress row when a slot announces its
        # metadata. Wired to vm.file_registered in connect_viewmodel; rows are
        # added in registration order (the order Android opens its slots).
        item = BackupFileDTO(
            path=rel_path,
            name=Path(rel_path).name,
            size_bytes=size_bytes,
        )
        row = _BackupFileRow(item, parent=self._scroll_content)
        self._rows[rel_path] = row
        self._statuses[rel_path] = BackupStatus.QUEUED
        self._scroll_layout.addWidget(row)

    @Slot(str, 'qint64', float)
    def _on_file_progress(self, path: str, bytes_done: int, speed_bps: float) -> None:
        # Route a progress tick from the ViewModel to the matching row widget.
        row = self._rows.get(path)
        if row is not None:
            row.update_progress(bytes_done, speed_bps)

    @Slot(str, object)
    def _on_file_status_changed(self, path: str, status: BackupStatus) -> None:
        # Propagate a status transition to the matching row and refresh summaries.
        row = self._rows.get(path)
        if row is not None:
            row.set_status(status)
        self._statuses[path] = status
        self._refresh_summary()
        self._refresh_tray_tooltip()

    @Slot('qint64', 'qint64', float)
    def _on_overall_updated(self, total_bytes: int, done_bytes: int, eta_secs: float) -> None:
        # Update the overall progress bar, stats, and ETA/elapsed label.
        if total_bytes > 0:
            pct = int(done_bytes / total_bytes * 100)
            self._overall_bar.set_percent(pct)
            self._overall_pct.setText(f"{pct}%")
        self._overall_stats.setText(self._build_stats_text())

        elapsed_secs = int((datetime.now() - self._started_at).total_seconds())
        elapsed_str = _fmt_elapsed(elapsed_secs)
        if eta_secs >= 0:
            self._overall_eta_label.setText(f"{_fmt_eta(eta_secs)}  ·  {elapsed_str}")
            self._overall_eta_label.setVisible(True)
        elif elapsed_secs > 0:
            self._overall_eta_label.setText(elapsed_str)
            self._overall_eta_label.setVisible(True)

        self._refresh_tray_tooltip()

    @Slot()
    def _on_backup_complete(self) -> None:
        # Lock the UI into the completed state.
        self._backup_done = True
        self._overall_bar.set_percent(100)
        self._overall_pct.setText("100%")
        self._overall_stats.setText("Backup complete  ✓")
        elapsed_secs = int((datetime.now() - self._started_at).total_seconds())
        self._overall_eta_label.setText(f"Finished in {_fmt_elapsed(elapsed_secs).replace(' elapsed', '')}")
        self._overall_eta_label.setVisible(True)
        self._pause_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._tray_icon.setToolTip("SyncDose — Backup complete ✓")

    @Slot(str)
    def _on_backup_error(self, error: str) -> None:
        # Surface a session-level error in the stats label.
        self._overall_stats.setText(f"Error: {error}")

    # ── User-action slots ─────────────────────────────────────────────────────

    @Slot()
    def _on_pause_clicked(self) -> None:
        # Toggle pause / resume state and emit the appropriate signal.
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
        # Sync the Pause/Resume button and tray action to is_paused. Driven by
        # BackupViewModel.pause_state_changed, which fires both for
        # PC-initiated pauses (via _on_pause_clicked's own pause_requested
        # round-trip) and Android-initiated pauses (via the sticky
        # notification). Avoid re-emitting pause_requested/resume_requested
        # here since the originating side already knows.
        if self._paused == is_paused:
            return
        self._paused = is_paused
        label = "▶  Resume" if is_paused else "⏸  Pause All"
        self._pause_btn.setText(label)
        self._tray_pause_act.setText(label)

    @Slot()
    def _on_cancel_requested(self) -> None:
        # Ask the user to confirm, then emit cancel_requested and close.
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

    def changeEvent(self, event: QEvent) -> None:
        """Intercept minimize → hide to tray.

        Args:
            event: The Qt change event being processed.
        """
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self.hide()
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ask for cancellation confirmation unless the backup is already done.

        The ``_cancelling`` flag lets a second close pass (triggered by
        :meth:`_on_cancel_requested`) through immediately without a second dialog.

        Args:
            event: The Qt close event; accepted or ignored based on the user's
                confirmation choice.
        """
        if self._cancelling or self._backup_done:
            self._tray_icon.hide()
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
            event.accept()
        else:
            event.ignore()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _refresh_summary(self) -> None:
        self._summary_label.setText(self._build_summary_text())

    def _refresh_tray_tooltip(self) -> None:
        self._tray_icon.setToolTip(f"SyncDose — Backup {self._overall_bar.percent}% complete")

    def _build_stats_text(self) -> str:
        done = sum(1 for s in self._statuses.values() if s == BackupStatus.DONE)
        return f"{done} of {self._total_files} file{'s' if self._total_files != 1 else ''} complete"

    def _build_summary_text(self) -> str:
        counts = {s: sum(1 for v in self._statuses.values() if v == s) for s in BackupStatus}
        parts: list[str] = []
        if counts[BackupStatus.DONE]:   parts.append(f"{counts[BackupStatus.DONE]} done")
        if counts[BackupStatus.ACTIVE]: parts.append(f"{counts[BackupStatus.ACTIVE]} syncing")
        if counts[BackupStatus.QUEUED]: parts.append(f"{counts[BackupStatus.QUEUED]} queued")
        if counts[BackupStatus.FAILED]: parts.append(f"{counts[BackupStatus.FAILED]} failed")
        return "  ·  ".join(parts) if parts else "No files"


# ── Standalone preview ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import resources_qrc  # noqa: F401 — registers Qt virtual resource paths

    _sample = [
        ("vacation_2022.webp", 3_456_000),
        ("portrait.heic", 8_200_000),
        ("family_video.mp4", 54_000_000),
        ("night_shot.jpg", 2_100_000),
        ("quarterly_report.pdf", 890_000),
        ("favourite_track.mp3", 5_400_000),
        ("photos_2024.zip", 120_000_000),
    ]

    app = QApplication(sys.argv)
    win = BackupProgressWindow(
        file_count=len(_sample),
        total_bytes=sum(s for _, s in _sample),
    )

    # Simulate lazy file registration (normally driven by vm.file_registered).
    for name, size in _sample:
        win._on_file_registered(name, size)

    # Simulate some in-progress state without a real ViewModel.
    win._rows["vacation_2022.webp"].set_status(BackupStatus.DONE)
    win._rows["vacation_2022.webp"].update_progress(3_456_000, 0)
    win._rows["portrait.heic"].set_status(BackupStatus.ACTIVE)
    win._rows["portrait.heic"].update_progress(3_280_000, 820_000)
    win._rows["quarterly_report.pdf"].set_status(BackupStatus.FAILED)
    win._statuses["vacation_2022.webp"] = BackupStatus.DONE
    win._statuses["portrait.heic"] = BackupStatus.ACTIVE
    win._statuses["quarterly_report.pdf"] = BackupStatus.FAILED
    win._refresh_summary()

    win.show()
    sys.exit(app.exec())

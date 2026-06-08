"""
Backup progress window.

A standalone :class:`QMainWindow` that tracks per-file backup progress for a
batch of files.  The window minimises to a dedicated system-tray icon; closing
it prompts the user to confirm cancellation of the backup.

The widget is **purely presentational** — it exposes a clean public API that a
future ``BackupViewModel`` can drive without this widget knowing anything about
services or repositories::

    from views.widgets.backup.backup_progress_window import (
        BackupProgressWindow, BackupProgressItem, BackupStatus,
    )

    items = [
        BackupProgressItem(path="C:/phone/dcim/photo.jpg", name="photo.jpg", size_bytes=3_000_000),
        BackupProgressItem(path="C:/phone/dcim/video.mp4", name="video.mp4", size_bytes=54_000_000),
    ]
    win = BackupProgressWindow(items)
    win.show()

    # From a ViewModel / Service thread (via queued signals):
    win.update_progress("C:/phone/dcim/photo.jpg", bytes_done=1_500_000, speed_bps=750_000)
    win.set_status("C:/phone/dcim/photo.jpg", BackupStatus.DONE)
    win.set_overall(total_bytes=57_000_000, done_bytes=3_000_000)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final

from PySide6.QtCore import Qt, QEvent, QRectF, QSize, Signal, Slot
from PySide6.QtGui import (
    QCloseEvent, QColor, QIcon, QImageReader, QPainter, QPainterPath, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QMessageBox, QPushButton, QScrollArea,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from app.theme_manager import theme_manager
from resources.colors import (
    BackupProgressColors, LightBackupProgressColors,
    Palette,
)
from resources.paths import BackupStyles, Icons
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from views.widgets.bar import Bar

# ── Layout constants ───────────────────────────────────────────────────────────
_WINDOW_MIN_WIDTH:  Final[int] = 620
_WINDOW_MIN_HEIGHT: Final[int] = 500
_WINDOW_MAX_HEIGHT: Final[int] = 820
_HEADER_ICON_SIZE:  Final[int] = 40
_ROW_ICON_SIZE:     Final[int] = 44
_BUTTON_HEIGHT:     Final[int] = 36
_STATUS_BADGE_W:    Final[int] = 90

# ── File-type extension sets ───────────────────────────────────────────────────
_IMAGE_EXTS: frozenset[str] = frozenset({
    "jpg", "jpeg", "png", "gif", "bmp", "webp",
    "tiff", "tif", "heic", "heif", "ico",
})
_VIDEO_EXTS:   frozenset[str] = frozenset({"mp4", "mov", "avi", "mkv", "wmv", "flv", "webm", "m4v"})
_AUDIO_EXTS:   frozenset[str] = frozenset({"mp3", "wav", "flac", "aac", "ogg", "wma", "m4a"})
_DOC_EXTS:     frozenset[str] = frozenset({"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv"})
_ARCHIVE_EXTS: frozenset[str] = frozenset({"zip", "rar", "7z", "tar", "gz", "bz2"})


def _ext(name: str) -> str:
    """Return the lowercase extension of *name*, or ``""`` if none."""
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _file_emoji(name: str) -> str:
    """Return a Unicode emoji that represents the file type of *name*."""
    e = _ext(name)
    if e in _IMAGE_EXTS:   return "🖼"
    if e in _VIDEO_EXTS:   return "🎬"
    if e in _AUDIO_EXTS:   return "🎵"
    if e in _DOC_EXTS:     return "📄"
    if e in _ARCHIVE_EXTS: return "📦"
    return "📁"


# ── Thumbnail helpers ──────────────────────────────────────────────────────────

def _make_rounded_pixmap(pixmap: QPixmap, radius: int) -> QPixmap:
    """Clip *pixmap* to a rounded rectangle, preserving transparency."""
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(result.rect()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result


def _load_thumb(path: str, size: int) -> QPixmap | None:
    """Load an image at *size* × *size* resolution with center-crop.

    Uses :class:`QImageReader` scaled-size hint for memory efficiency.
    Returns ``None`` if the file is missing, corrupt, or an unsupported format.
    """
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    original = reader.size()
    if not original.isValid():
        return None
    hint = QSize(size * 2, size * 2)
    reader.setScaledSize(
        original.scaled(hint, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
    )
    image = reader.read()
    if image.isNull():
        return None
    pixmap = QPixmap.fromImage(image)
    w, h = pixmap.width(), pixmap.height()
    if w > size or h > size:
        x = max(0, (w - size) // 2)
        y = max(0, (h - size) // 2)
        pixmap = pixmap.copy(x, y, min(w, size), min(h, size))
    pixmap = pixmap.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return _make_rounded_pixmap(pixmap, radius=8)


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _fmt_size(size_bytes: int) -> str:
    """Return a concise human-readable byte-size string (e.g. ``"2.3 MB"``)."""
    if size_bytes < 1_024:       return f"{size_bytes} B"
    if size_bytes < 1_024 ** 2:  return f"{size_bytes / 1_024:.1f} KB"
    if size_bytes < 1_024 ** 3:  return f"{size_bytes / 1_024 ** 2:.1f} MB"
    return f"{size_bytes / 1_024 ** 3:.1f} GB"


def _fmt_speed_eta(speed_bps: float, remaining_bytes: int) -> str:
    """Format a speed + ETA string, e.g. ``"2.3 MB/s  ·  12s left"``."""
    if speed_bps <= 0:
        return ""
    speed_str = _fmt_size(int(speed_bps)) + "/s"
    secs = remaining_bytes / speed_bps
    if secs < 60:
        eta = f"{int(secs)}s left"
    elif secs < 3600:
        eta = f"{int(secs / 60)}m left"
    else:
        eta = f"{secs / 3600:.1f}h left"
    return f"{speed_str}  ·  {eta}"


# ── Data model ─────────────────────────────────────────────────────────────────

class BackupStatus(StrEnum):
    """Lifecycle state of a single file in the backup queue."""
    QUEUED = "queued"
    ACTIVE = "active"
    DONE   = "done"
    FAILED = "failed"


@dataclass
class BackupProgressItem:
    """Descriptor for one file in the backup queue.

    Args:
        path: Absolute path to the source file on disk (used as the dict key).
        name: Display name shown in the row (typically ``Path(path).name``).
        size_bytes: Total byte count of the file.
        status: Current :class:`BackupStatus`; defaults to :attr:`~BackupStatus.QUEUED`.
        bytes_done: Bytes transferred so far; updated by :meth:`BackupProgressWindow.update_progress`.
        speed_bps: Current transfer speed in bytes/second; updated alongside *bytes_done*.
    """
    path:       str
    name:       str
    size_bytes: int
    status:     BackupStatus = field(default=BackupStatus.QUEUED)
    bytes_done: int          = 0
    speed_bps:  float        = 0.0


# ── File row widget ────────────────────────────────────────────────────────────

class _BackupFileRow(QFrame):
    """Single file entry in the backup progress list.

    Displays a file-type icon (thumbnail for images, emoji for everything else),
    filename, size, an inline :class:`~views.widgets.bar.Bar` progress bar
    (visible only when *active*), speed + ETA, and a status badge.

    The ``status`` dynamic property drives all QSS colour-state selectors.
    Call :meth:`set_status` and :meth:`update_progress` to refresh the row.
    """

    def __init__(self, item: BackupProgressItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item = item
        self._setup_ui()

    # ── Public API ────────────────────────────────────────────────────────────

    def update_progress(self, bytes_done: int, speed_bps: float) -> None:
        """Refresh the inline bar fill and speed / ETA label.

        Args:
            bytes_done: Number of bytes transferred so far.
            speed_bps: Current transfer speed in bytes per second.
        """
        self._item.bytes_done = bytes_done
        self._item.speed_bps  = speed_bps
        pct = int(bytes_done / self._item.size_bytes * 100) if self._item.size_bytes else 0
        self._row_bar.set_percent(pct)
        remaining = max(0, self._item.size_bytes - bytes_done)
        self._speed_label.setText(_fmt_speed_eta(speed_bps, remaining))

    def set_status(self, status: BackupStatus) -> None:
        """Transition the row to *status*, updating QSS state and visibility.

        Args:
            status: The new :class:`BackupStatus` for this row.
        """
        self._item.status = status
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
        self.setProperty("status", self._item.status.value)
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        self._icon_label   = self._create_icon()
        self._name_label   = self._create_name_label()
        self._size_label   = self._create_size_label()
        self._row_bar      = self._create_row_bar()
        self._speed_label  = self._create_speed_label()
        self._status_badge = self._create_status_badge()

    def _create_icon(self) -> QLabel:
        """Return a thumbnail for image files, or an emoji label for all others."""
        lbl = QLabel()
        lbl.setObjectName("FileTypeIcon")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedSize(_ROW_ICON_SIZE, _ROW_ICON_SIZE)

        if _ext(self._item.name) in _IMAGE_EXTS:
            pixmap = _load_thumb(self._item.path, _ROW_ICON_SIZE)
            if pixmap is not None:
                lbl.setPixmap(pixmap)
                return lbl

        lbl.setText(_file_emoji(self._item.name))
        return lbl

    def _create_name_label(self) -> QLabel:
        lbl = QLabel(self._item.name)
        lbl.setObjectName("RowFileName")
        lbl.setToolTip(self._item.path)   # full path visible on hover
        return lbl

    def _create_size_label(self) -> QLabel:
        lbl = QLabel(_fmt_size(self._item.size_bytes))
        lbl.setObjectName("RowFileSize")
        return lbl

    def _create_row_bar(self) -> Bar:
        """Inline gradient progress bar — hidden until status → active."""
        pct = int(self._item.bytes_done / self._item.size_bytes * 100) if self._item.size_bytes else 0
        bar = Bar(pct, QColor(Palette.CYAN_400), QColor(Palette.TEAL_400))
        bar.setVisible(self._item.status == BackupStatus.ACTIVE)
        return bar

    def _create_speed_label(self) -> QLabel:
        remaining = max(0, self._item.size_bytes - self._item.bytes_done)
        lbl = QLabel(_fmt_speed_eta(self._item.speed_bps, remaining))
        lbl.setObjectName("RowSpeed")
        lbl.setVisible(self._item.status == BackupStatus.ACTIVE)
        return lbl

    def _create_status_badge(self) -> QLabel:
        lbl = QLabel(_badge_text(self._item.status))
        lbl.setObjectName("StatusBadge")
        lbl.setProperty("status", self._item.status.value)
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


def _badge_text(status: BackupStatus) -> str:
    """Return the short display string for a status badge."""
    return {
        BackupStatus.QUEUED: "Queued",
        BackupStatus.ACTIVE: "● Syncing",
        BackupStatus.DONE:   "✓  Done",
        BackupStatus.FAILED: "✗  Failed",
    }[status]


# ── Main window ────────────────────────────────────────────────────────────────

class BackupProgressWindow(QMainWindow):
    """Standalone window showing per-file backup progress.

    Opens alongside the main SyncDose dashboard (same process, separate window).
    Minimising hides it to a **dedicated** :class:`~PySide6.QtWidgets.QSystemTrayIcon`;
    double-clicking the tray icon restores the window.  Closing the window
    prompts for cancellation confirmation.

    Drive from a future ``BackupViewModel``::

        win.update_progress(path, bytes_done=1_500_000, speed_bps=750_000)
        win.set_status(path, BackupStatus.DONE)
        win.set_overall(total_bytes=20_000_000, done_bytes=3_000_000)

    Signals:
        pause_requested:  Emitted when the user clicks **Pause All** (stub).
        resume_requested: Emitted when the user clicks **Resume** (stub).
        cancel_requested: Emitted after the user confirms cancellation.
    """

    pause_requested:  Signal = Signal()
    resume_requested: Signal = Signal()
    cancel_requested: Signal = Signal()

    def __init__(
            self,
            items: list[BackupProgressItem],
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items:       list[BackupProgressItem]  = items
        self._rows:        dict[str, _BackupFileRow] = {}
        self._paused:      bool                      = False
        self._backup_done: bool                      = False   # skips cancel-confirm on close
        self._cancelling:  bool                      = False   # prevents double close-event dialog
        self._started_at:  datetime                  = datetime.now()

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── Public API ────────────────────────────────────────────────────────────

    def update_progress(self, path: str, bytes_done: int, speed_bps: float = 0.0) -> None:
        """Update the per-file progress bar and speed / ETA for *path*.

        Also recomputes the overall progress bar via :meth:`_refresh_overall`.

        Args:
            path: Absolute path of the file being backed up.
            bytes_done: Bytes transferred so far for this file.
            speed_bps: Current transfer speed in bytes per second (0 = unknown).
        """
        row = self._rows.get(path)
        if row is not None:
            row.update_progress(bytes_done, speed_bps)
            for item in self._items:
                if item.path == path:
                    item.bytes_done = bytes_done
                    item.speed_bps  = speed_bps
                    break
        self._refresh_overall()

    def set_status(self, path: str, status: BackupStatus) -> None:
        """Change the visual state of a single file row.

        Args:
            path: Absolute path of the affected file.
            status: The new :class:`BackupStatus` for that file.
        """
        row = self._rows.get(path)
        if row is not None:
            row.set_status(status)
        for item in self._items:
            if item.path == path:
                item.status = status
                break
        self._refresh_summary()
        self._refresh_tray_tooltip()

    def set_overall(self, total_bytes: int, done_bytes: int) -> None:
        """Directly set the overall progress bar values.

        Prefer calling :meth:`update_progress` per file and letting
        :meth:`_refresh_overall` derive the totals automatically.  Use this
        method when the caller has authoritative totals.

        Args:
            total_bytes: Total byte count across all files.
            done_bytes: Bytes transferred so far across all files.
        """
        if total_bytes > 0:
            pct = int(done_bytes / total_bytes * 100)
            self._overall_bar.set_percent(pct)
            self._overall_pct.setText(f"{pct}%")
        self._refresh_tray_tooltip()

    def mark_done(self) -> None:
        """Mark the entire backup as complete and lock the action buttons."""
        self._backup_done = True
        self._overall_bar.set_percent(100)
        self._overall_pct.setText("100%")
        self._overall_stats.setText("Backup complete  ✓")
        self._pause_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._tray_icon.setToolTip("SyncDose — Backup complete ✓")

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
        self._header           = self._create_header()
        self._overall_section  = self._create_overall_section()
        self._scroll_area      = self._create_scroll_area()
        self._summary_label    = self._create_summary_label()
        self._pause_btn        = self._create_pause_button()
        self._cancel_btn       = self._create_cancel_button()

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

        n = len(self._items)
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
        """Elevated card showing the overall progress bar, percentage and stats."""
        container = QWidget()
        container.setObjectName("OverallSection")

        # Custom Bar widget (matches the project's existing progress-bar pattern)
        self._overall_bar = Bar(
            0,
            QColor(Palette.CYAN_400),
            QColor(Palette.TEAL_400),
        )
        self._overall_bar.setFixedHeight(10)

        self._overall_pct = QLabel("0%")
        self._overall_pct.setObjectName("OverallPercent")
        self._overall_pct.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._overall_pct.setFixedWidth(52)

        self._overall_stats = QLabel(self._build_stats_text())
        self._overall_stats.setObjectName("OverallStats")

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
        return container

    # ── Scroll area ───────────────────────────────────────────────────────────

    def _create_scroll_area(self) -> QScrollArea:
        content = QWidget()
        content.setObjectName("FileScrollContent")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.SM)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        if self._items:
            for item in self._items:
                row = _BackupFileRow(item, parent=content)
                self._rows[item.path] = row
                layout.addWidget(row)
        else:
            empty = QLabel("No files queued for backup.")
            empty.setObjectName("EmptyLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty)

        scroll = QScrollArea()
        scroll.setObjectName("FileScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(content)
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
        """Create the dedicated system-tray icon with a backup context menu."""
        self._tray_icon = QSystemTrayIcon(QIcon(Icons.LOGO), parent=self)
        self._tray_icon.setToolTip("SyncDose — Backup in progress…")

        self._tray_menu = QMenu()
        open_action          = self._tray_menu.addAction("Open Backup Progress")
        self._tray_menu.addSeparator()
        self._tray_pause_act = self._tray_menu.addAction("⏸  Pause All")
        cancel_action        = self._tray_menu.addAction("✗  Cancel Backup")

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

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot()
    def _on_pause_clicked(self) -> None:
        """Toggle pause / resume state (stub — backend not yet wired)."""
        self._paused = not self._paused
        if self._paused:
            self._pause_btn.setText("▶  Resume")
            self._tray_pause_act.setText("▶  Resume")
            self.pause_requested.emit()
        else:
            self._pause_btn.setText("⏸  Pause All")
            self._tray_pause_act.setText("⏸  Pause All")
            self.resume_requested.emit()

    @Slot()
    def _on_cancel_requested(self) -> None:
        """Ask the user to confirm, then emit :attr:`cancel_requested` and close."""
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
        """Intercept minimize → hide to tray (mirrors ``MainWindow`` pattern)."""
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self.hide()
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ask for cancellation confirmation unless the backup is already done.

        Guards against a double-dialog when :meth:`_on_cancel_requested` calls
        ``self.close()`` after the user already confirmed — the ``_cancelling``
        flag lets that second pass through immediately.
        """
        # Already confirmed cancellation, or backup completed naturally.
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

    def _refresh_overall(self) -> None:
        """Recompute the overall % from accumulated per-item byte counts."""
        total = sum(i.size_bytes  for i in self._items)
        done  = sum(i.bytes_done  for i in self._items)
        self.set_overall(total, done)
        self._overall_stats.setText(self._build_stats_text())

    def _refresh_summary(self) -> None:
        self._summary_label.setText(self._build_summary_text())

    def _refresh_tray_tooltip(self) -> None:
        self._tray_icon.setToolTip(f"SyncDose — Backup {self._overall_bar.percent}% complete")

    def _build_stats_text(self) -> str:
        done  = sum(1 for i in self._items if i.status == BackupStatus.DONE)
        total = len(self._items)
        return f"{done} of {total} file{'s' if total != 1 else ''} complete"

    def _build_summary_text(self) -> str:
        counts = {s: sum(1 for i in self._items if i.status == s) for s in BackupStatus}
        parts: list[str] = []
        if counts[BackupStatus.DONE]:   parts.append(f"{counts[BackupStatus.DONE]} done")
        if counts[BackupStatus.ACTIVE]: parts.append(f"{counts[BackupStatus.ACTIVE]} syncing")
        if counts[BackupStatus.QUEUED]: parts.append(f"{counts[BackupStatus.QUEUED]} queued")
        if counts[BackupStatus.FAILED]: parts.append(f"{counts[BackupStatus.FAILED]} failed")
        return "  ·  ".join(parts) if parts else "No files"


# ── Standalone preview ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import resources_qrc  # noqa: F401 — registers Qt virtual resource paths

    sample_items = [
        BackupProgressItem(
            r"C:\Users\Lavi\OneDrive - Bar-Ilan University - Students\Photos\My Photos\2022\2-February\9725.webp",
            "vacation_2022.webp", 3_456_000, BackupStatus.DONE, 3_456_000,
        ),
        BackupProgressItem(
            "C:/phone/dcim/portrait.heic",
            "portrait.heic", 8_200_000, BackupStatus.ACTIVE, 3_280_000, 820_000,
        ),
        BackupProgressItem(
            "C:/phone/dcim/family_video.mp4",
            "family_video.mp4", 54_000_000,
        ),
        BackupProgressItem(
            "C:/phone/dcim/night_shot.jpg",
            "night_shot.jpg", 2_100_000,
        ),
        BackupProgressItem(
            "C:/phone/docs/quarterly_report.pdf",
            "quarterly_report.pdf", 890_000, BackupStatus.FAILED,
        ),
        BackupProgressItem(
            "C:/phone/music/favourite_track.mp3",
            "favourite_track.mp3", 5_400_000,
        ),
        BackupProgressItem(
            "C:/phone/archives/photos_2024.zip",
            "photos_2024.zip", 120_000_000,
        ),
    ]

    app = QApplication(sys.argv)
    win = BackupProgressWindow(sample_items)
    win.show()
    sys.exit(app.exec())

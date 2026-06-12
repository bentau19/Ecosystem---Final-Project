from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple

from PySide6.QtCore import Qt, QAbstractListModel, QModelIndex, QObject, QThreadPool, Slot
from PySide6.QtGui import QPixmap

from domain.enums.backup_status import BackupStatus
from resources.colors import BackupProgressColors, LightBackupProgressColors
from utils.file_type import IMAGE_EXTS, file_ext
from views.widgets.backup.helpers import ThumbLoader, ThumbResult

# ── Shared layout constant (also imported by the delegate) ────────────────────
ROW_ICON_SIZE: Final[int] = 44

# ── Custom model roles ────────────────────────────────────────────────────────
NameRole:      Final[int] = Qt.ItemDataRole.UserRole + 1
SizeRole:      Final[int] = Qt.ItemDataRole.UserRole + 2
BytesDoneRole: Final[int] = Qt.ItemDataRole.UserRole + 3
SpeedRole:     Final[int] = Qt.ItemDataRole.UserRole + 4
StatusRole:    Final[int] = Qt.ItemDataRole.UserRole + 5
ThumbRole:     Final[int] = Qt.ItemDataRole.UserRole + 6


# ── Color tokens ──────────────────────────────────────────────────────────────

class ProgressColors(NamedTuple):
    background:        str
    row_bg:            str
    row_border:        str
    row_active_bg:     str
    row_active_border: str
    text_primary:      str
    text_secondary:    str
    progress_track:    str
    progress_fill:     str
    progress_fill_end: str
    queued_text:       str
    active_bg:         str
    active_text:       str
    done_bg:           str
    done_text:         str
    failed_bg:         str
    failed_text:       str
    skipped_bg:        str
    skipped_text:      str


def make_colors(is_dark: bool) -> ProgressColors:
    cls = BackupProgressColors if is_dark else LightBackupProgressColors
    m = cls.__members__
    return ProgressColors(
        background=m["BACKGROUND"].value,
        row_bg=m["ROW_BG"].value,
        row_border=m["ROW_BORDER"].value,
        row_active_bg=m["ROW_ACTIVE_BG"].value,
        row_active_border=m["ROW_ACTIVE_BORDER"].value,
        text_primary=m["TEXT_PRIMARY"].value,
        text_secondary=m["TEXT_SECONDARY"].value,
        progress_track=m["PROGRESS_TRACK"].value,
        progress_fill=m["PROGRESS_FILL"].value,
        progress_fill_end=m["PROGRESS_FILL_END"].value,
        queued_text=m["STATUS_QUEUED_TEXT"].value,
        active_bg=m["STATUS_ACTIVE_BG"].value,
        active_text=m["STATUS_ACTIVE_TEXT"].value,
        done_bg=m["STATUS_DONE_BG"].value,
        done_text=m["STATUS_DONE_TEXT"].value,
        failed_bg=m["STATUS_FAILED_BG"].value,
        failed_text=m["STATUS_FAILED_TEXT"].value,
        skipped_bg=m["STATUS_SKIPPED_BG"].value,
        skipped_text=m["STATUS_SKIPPED_TEXT"].value,
    )


# ── Per-file entry ────────────────────────────────────────────────────────────

@dataclass
class FileEntry:
    path: str
    name: str
    size_bytes: int
    bytes_done: int = 0
    speed_bps: float = 0.0
    status: BackupStatus = BackupStatus.QUEUED


# ── Model ─────────────────────────────────────────────────────────────────────

class BackupProgressModel(QAbstractListModel):
    """Live model for the backup progress list.

    Files are registered lazily as ``file_registered`` signals arrive from the
    ViewModel.  Per-file progress and status are updated in O(1) via
    :attr:`_index`.  Incremental counters in :attr:`_counts` avoid O(n)
    summary iteration.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[FileEntry] = []
        self._index: dict[str, int] = {}        # path → row index
        self._thumbs: dict[str, QPixmap | None] = {}
        self._counts: dict[BackupStatus, int] = {s: 0 for s in BackupStatus}
        # Lazy thumbnail state — abs_path is stored by trigger_thumb() once the
        # file is confirmed on disk; _loading tracks in-flight workers so we
        # never start a duplicate ThumbLoader for the same key.
        self._abs_paths: dict[str, str] = {}    # key → absolute disk path
        self._loading:   set[str]       = set() # keys with a ThumbLoader in-flight

        self._result = ThumbResult(self)
        self._result.ready.connect(self._on_thumb_ready)

    # ── QAbstractListModel interface ──────────────────────────────────────────

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._entries)):
            return None
        e = self._entries[index.row()]
        if role == NameRole:      return e.name
        if role == SizeRole:      return e.size_bytes
        if role == BytesDoneRole: return e.bytes_done
        if role == SpeedRole:     return e.speed_bps
        if role == StatusRole:    return e.status
        if role == ThumbRole:
            # Lazy load: start a ThumbLoader only the first time this row's
            # thumbnail is requested by the delegate (i.e. when it is in the
            # visible viewport).  abs_path is populated by trigger_thumb() once
            # the file is confirmed saved to disk — before that we have nothing
            # to read so we just return None (the delegate shows the placeholder).
            key    = e.path
            cached = self._thumbs.get(key)
            if cached is None and key not in self._loading:
                abs_path = self._abs_paths.get(key)
                if abs_path is not None:
                    self._loading.add(key)
                    QThreadPool.globalInstance().start(
                        ThumbLoader(key, abs_path, ROW_ICON_SIZE, self._result)
                    )
            return cached
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled

    # ── Public API ────────────────────────────────────────────────────────────

    def register_file(self, path: str, size_bytes: int) -> None:
        """Append a new file entry.

        Thumbnail loading is deferred until the file is confirmed saved to
        disk (DONE status) — see :meth:`trigger_thumb`.
        """
        row = len(self._entries)
        self.beginInsertRows(QModelIndex(), row, row)
        self._entries.append(FileEntry(
            path=path,
            name=Path(path).name,
            size_bytes=size_bytes,
            status=BackupStatus.QUEUED,
        ))
        self._index[path] = row
        self._counts[BackupStatus.QUEUED] += 1
        self.endInsertRows()

    def update_progress(self, path: str, bytes_done: int, speed_bps: float) -> None:
        """Update byte progress and speed for a file."""
        row = self._index.get(path)
        if row is None:
            return
        e = self._entries[row]
        e.bytes_done = bytes_done
        e.speed_bps = speed_bps
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [BytesDoneRole, SpeedRole])

    def update_status(self, path: str, status: BackupStatus) -> None:
        """Transition a file to a new status, maintaining O(1) counters."""
        row = self._index.get(path)
        if row is None:
            return
        e = self._entries[row]
        self._counts[e.status] = max(0, self._counts[e.status] - 1)
        self._counts[status] += 1
        e.status = status
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [StatusRole])

    def trigger_thumb(self, key: str, abs_path: str) -> None:
        """Record the on-disk path once a file is confirmed saved, then signal the row.

        Does **not** start a :class:`~helpers.ThumbLoader` here.  Instead it
        stores ``abs_path`` so that the lazy branch in :meth:`data` can pick it
        up the next time the delegate paints this row (i.e. when it is in the
        visible viewport).  Emitting ``dataChanged`` immediately triggers a
        repaint for rows that are currently visible, while off-screen rows are
        left untouched — no disk I/O occurs for rows the user has not seen.

        Non-image files are silently ignored; their emoji placeholder remains.
        """
        if file_ext(Path(key).name) not in IMAGE_EXTS:
            return
        self._abs_paths[key] = abs_path
        row = self._index.get(key)
        if row is not None:
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [ThumbRole])

    def summary_counts(self) -> dict[BackupStatus, int]:
        """Return the current per-status counts (O(1) — read from counters)."""
        return dict(self._counts)

    # ── Thumb slot ────────────────────────────────────────────────────────────

    @Slot(str, object)
    def _on_thumb_ready(self, path: str, pixmap: object) -> None:
        self._loading.discard(path)          # loader finished — clear in-flight guard
        self._thumbs[path] = pixmap          # type: ignore[assignment]
        row = self._index.get(path)
        if row is not None:
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [ThumbRole])

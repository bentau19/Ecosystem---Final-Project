from __future__ import annotations

from typing import Final, NamedTuple

from PySide6.QtCore import Qt, QAbstractListModel, QModelIndex, QObject, QThreadPool, Slot
from PySide6.QtGui import QPixmap

from domain.dto.backup_file import BackupFileDTO
from resources.colors import BackupReviewColors, LightBackupReviewColors
from views.widgets.backup.helpers import ThumbLoader, ThumbResult

# ── Shared layout constant (also imported by the delegate) ────────────────────
THUMB_SIZE: Final[int] = 56

# ── Custom model roles ────────────────────────────────────────────────────────
PathRole:     Final[int] = Qt.ItemDataRole.UserRole + 1
NameRole:     Final[int] = Qt.ItemDataRole.UserRole + 2
SizeRole:     Final[int] = Qt.ItemDataRole.UserRole + 3
MtimeRole:    Final[int] = Qt.ItemDataRole.UserRole + 4
DecisionRole: Final[int] = Qt.ItemDataRole.UserRole + 5
ThumbRole:    Final[int] = Qt.ItemDataRole.UserRole + 6


# ── Color tokens ──────────────────────────────────────────────────────────────

class ReviewColors(NamedTuple):
    background:     str
    row_bg:         str
    row_border:     str
    row_hover:      str
    keep_bg:        str
    keep_border:    str
    keep_text:      str
    delete_bg:      str
    delete_border:  str
    delete_text:    str
    icon_bg:        str
    icon_border:    str
    icon_text:      str
    text_primary:   str
    text_secondary: str


def make_colors(is_dark: bool) -> ReviewColors:
    cls = BackupReviewColors if is_dark else LightBackupReviewColors
    m = cls.__members__
    return ReviewColors(
        background=m["BACKGROUND"].value,
        row_bg=m["ROW_BG"].value,
        row_border=m["ROW_BORDER"].value,
        row_hover=m["ROW_HOVER"].value,
        keep_bg=m["KEEP_BG"].value,
        keep_border=m["KEEP_BORDER"].value,
        keep_text=m["KEEP_TEXT"].value,
        delete_bg=m["DELETE_BG"].value,
        delete_border=m["DELETE_BORDER"].value,
        delete_text=m["DELETE_TEXT"].value,
        icon_bg=m["ICON_BG"].value,
        icon_border=m["ICON_BORDER"].value,
        icon_text=m["ICON_TEXT"].value,
        text_primary=m["TEXT_PRIMARY"].value,
        text_secondary=m["TEXT_SECONDARY"].value,
    )


# ── Model ─────────────────────────────────────────────────────────────────────

class BackupReviewModel(QAbstractListModel):
    """Stores backup file data and per-file Keep/Delete decisions.

    Thumbnails are loaded **lazily**: a :class:`~helpers.ThumbLoader` is
    started for a given row only the first time the delegate calls
    ``data(index, ThumbRole)`` — i.e. only when that row actually enters the
    visible viewport.  Rows the user never scrolls to never incur any disk I/O.
    When the loader finishes, ``dataChanged`` is emitted for that row so the
    delegate repaints with the real thumbnail.
    """

    def __init__(self, files: list[BackupFileDTO], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._files: list[BackupFileDTO] = list(files)  # mutable copy — rows are removed by apply_decided()
        self._decisions: dict[str, str] = {f.path: "pending" for f in files}
        self._applied_decisions: dict[str, str] = {}    # decisions committed via apply_decided()
        self._thumbs: dict[str, QPixmap | None] = {}
        # Tracks paths whose ThumbLoader is currently in-flight so we never
        # dispatch a second concurrent loader for the same file.
        self._loading: set[str] = set()

        # One result carrier — connect once, reused by every loader.
        self._result = ThumbResult(self)
        self._result.ready.connect(self._on_thumb_ready)

    # ── QAbstractListModel interface ──────────────────────────────────────────

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._files)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._files)):
            return None
        f = self._files[index.row()]
        if role == PathRole:     return f.path
        if role == NameRole:     return f.name
        if role == SizeRole:     return f.size_bytes
        if role == MtimeRole:    return f.mtime
        if role == DecisionRole: return self._decisions[f.path]
        if role == ThumbRole:
            # Lazy load: kick off a ThumbLoader the first time this row's
            # thumbnail is requested (i.e. when it scrolls into the viewport).
            # If already cached or a loader is already in-flight, return
            # immediately without starting a duplicate worker.
            cached = self._thumbs.get(f.path)
            if cached is None and f.path not in self._loading:
                self._loading.add(f.path)
                QThreadPool.globalInstance().start(
                    ThumbLoader(f.path, f.path, THUMB_SIZE, self._result)
                )
            return cached
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled

    # ── Public API ────────────────────────────────────────────────────────────

    def set_decision(self, row: int, decision: str) -> None:
        """Update the decision for the given row and notify the view."""
        if not (0 <= row < len(self._files)):
            return
        path = self._files[row].path
        self._decisions[path] = decision
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [DecisionRole])

    def apply_decided(self) -> int:
        """Remove all non-pending rows from the live model and park their decisions.

        Decided rows disappear from the list view immediately; their decisions are
        accumulated in ``_applied_decisions`` so :meth:`get_decisions` still returns
        them when the dialog eventually closes.

        Returns the number of rows removed.
        """
        decided_rows = [
            i for i, f in enumerate(self._files)
            if self._decisions[f.path] != "pending"
        ]
        if not decided_rows:
            return 0
        # Remove in reverse order so earlier indices remain valid during iteration.
        for row in reversed(decided_rows):
            f = self._files[row]
            self.beginRemoveRows(QModelIndex(), row, row)
            self._applied_decisions[f.path] = self._decisions.pop(f.path)
            self._files.pop(row)
            self.endRemoveRows()
        return len(decided_rows)

    def get_decisions(self) -> dict[str, str]:
        """Return ``{path: decision}`` for every non-pending row (current + applied)."""
        current = {p: d for p, d in self._decisions.items() if d != "pending"}
        return {**self._applied_decisions, **current}

    def decision_counts(self) -> tuple[int, int, int]:
        """Return ``(keep, delete, pending)`` counts."""
        keep = delete = pending = 0
        for d in self._decisions.values():
            if d == "keep":     keep    += 1
            elif d == "delete": delete  += 1
            else:               pending += 1
        return keep, delete, pending

    # ── Thumb slot ────────────────────────────────────────────────────────────

    @Slot(str, object)
    def _on_thumb_ready(self, path: str, pixmap: object) -> None:
        self._loading.discard(path)          # loader is done — allow future retries if needed
        self._thumbs[path] = pixmap          # type: ignore[assignment]
        for row, f in enumerate(self._files):
            if f.path == path:
                idx = self.index(row)
                self.dataChanged.emit(idx, idx, [ThumbRole])
                return

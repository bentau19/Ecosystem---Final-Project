from __future__ import annotations

import sys
from datetime import datetime
from typing import Final

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.theme_manager import theme_manager
from domain.dto.backup_file import BackupFileDTO
from resources.colors import BackupReviewColors, LightBackupReviewColors
from resources.paths import BackupStyles
from resources.spacing import Spacing
from utils.file_type import IMAGE_EXTS, file_ext, fmt_size
from utils.styles import load_stylesheet, themed
from views.widgets.backup.helpers import load_thumb

# ── Layout constants ──────────────────────────────────────────────────────────
_DIALOG_MIN_WIDTH:  Final[int] = 580
_DIALOG_MIN_HEIGHT: Final[int] = 420
_DIALOG_MAX_HEIGHT: Final[int] = 700
_ROW_HEIGHT:        Final[int] = 72   # taller to give the thumbnail room
_THUMB_SIZE:        Final[int] = 56   # square thumbnail side length (px)
_BUTTON_HEIGHT:     Final[int] = 30
_BUTTON_WIDTH:      Final[int] = 88


# ── File row widget ───────────────────────────────────────────────────────────

class _BackupFileRow(QFrame):
    """Single file entry showing name, meta info, and Keep / Delete toggle buttons.

    The row's ``decision`` dynamic property drives the QSS colour state:
    ``"pending"`` (default) → ``"keep"`` → ``"delete"``.  Clicking an already-
    active button resets it back to ``"pending"``.

    Emits :attr:`decision_changed` whenever the decision flips so the parent
    dialog can refresh its footer summary label.
    """

    decision_changed = Signal(str)  # "pending" | "keep" | "delete"

    def __init__(self, backup_file: BackupFileDTO, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._file: BackupFileDTO = backup_file
        self._decision: str = "pending"

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def decision(self) -> str:
        """Get the current decision for this row.

        Returns:
            ``"pending"``, ``"keep"``, or ``"delete"``.
        """
        return self._decision

    @property
    def file_path(self) -> str:
        """Get the absolute path of the represented backup file.

        Returns:
            The backup file's absolute filesystem path.
        """
        return self._file.path

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("BackupFileRow")
        self.setProperty("decision", "pending")
        self.setFixedHeight(_ROW_HEIGHT)
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        self._thumb_label: QLabel      = self._create_thumb_label()
        self._name_label:  QLabel      = self._create_name_label()
        self._meta_label:  QLabel      = self._create_meta_label()
        self._keep_btn:    QPushButton = self._create_keep_button()
        self._delete_btn:  QPushButton = self._create_delete_button()

    def _create_thumb_label(self) -> QLabel:
        # Load the image thumbnail; fall back to a cyan "IMG" circle if unreadable.
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)

        pixmap = load_thumb(self._file.path, _THUMB_SIZE)
        if pixmap is not None:
            lbl.setObjectName("FileThumb")
            lbl.setPixmap(pixmap)
        else:
            # File unreadable (missing, corrupt, or unsupported format).
            lbl.setObjectName("FileThumbFallback")
            lbl.setText("IMG")

        return lbl

    def _create_name_label(self) -> QLabel:
        lbl = QLabel(self._file.name)
        lbl.setObjectName("FileName")
        lbl.setToolTip(self._file.path)  # full path visible on hover
        return lbl

    def _create_meta_label(self) -> QLabel:
        size_str = fmt_size(self._file.size_bytes)
        if self._file.mtime:
            date_str = datetime.fromtimestamp(self._file.mtime / 1000).strftime("%b %d, %Y")
        else:
            date_str = "—"
        lbl = QLabel(f"{size_str}  ·  {date_str}")
        lbl.setObjectName("FileMeta")
        return lbl

    def _create_keep_button(self) -> QPushButton:
        btn = QPushButton("✓  Keep")
        btn.setObjectName("KeepButton")
        btn.setProperty("active", False)
        btn.setFixedSize(_BUTTON_WIDTH, _BUTTON_HEIGHT)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _create_delete_button(self) -> QPushButton:
        btn = QPushButton("✗  Delete")
        btn.setObjectName("DeleteButton")
        btn.setProperty("active", False)
        btn.setFixedSize(_BUTTON_WIDTH, _BUTTON_HEIGHT)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _setup_layout(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)
        root.setSpacing(Spacing.MD)

        root.addWidget(self._thumb_label, 0, Qt.AlignmentFlag.AlignVCenter)

        # Filename stacked above meta info, expanding to fill available width
        info = QVBoxLayout()
        info.setSpacing(2)
        info.setContentsMargins(0, 0, 0, 0)
        info.addWidget(self._name_label)
        info.addWidget(self._meta_label)
        root.addLayout(info, 1)

        root.addWidget(self._keep_btn,   0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(self._delete_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        # Style cascades from the parent dialog's setStyleSheet — nothing to do here.
        pass

    def _refresh_decision_style(self) -> None:
        # Re-polish the row and buttons so QSS dynamic-property selectors update.
        self.setProperty("decision", self._decision)
        self.style().unpolish(self)
        self.style().polish(self)

        for btn, is_active in (
            (self._keep_btn,   self._decision == "keep"),
            (self._delete_btn, self._decision == "delete"),
        ):
            btn.setProperty("active", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ── Signals ───────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._keep_btn.clicked.connect(self._on_keep_clicked)
        self._delete_btn.clicked.connect(self._on_delete_clicked)

    @Slot()
    def _on_keep_clicked(self) -> None:
        # Toggle: clicking an active button resets it back to "pending".
        self._decision = "pending" if self._decision == "keep" else "keep"
        self._refresh_decision_style()
        self.decision_changed.emit(self._decision)

    @Slot()
    def _on_delete_clicked(self) -> None:
        self._decision = "pending" if self._decision == "delete" else "delete"
        self._refresh_decision_style()
        self.decision_changed.emit(self._decision)


# ── Main dialog ───────────────────────────────────────────────────────────────

class BackupReviewDialog(QDialog):
    """Modal dialog for reviewing and approving backup file decisions.

    Shows a scrollable card list of backup image files.  Each row has
    **✓ Keep** / **✗ Delete** toggle buttons.  A live footer summary counts the
    current decisions.  Clicking **Apply Decisions** resolves the dialog as
    ``Accepted``; the caller reads :meth:`get_decisions` to act on the result.

    Non-image files are silently filtered out on construction.  Files still in
    ``"pending"`` state (no button clicked) are **omitted** from
    :meth:`get_decisions`.

    Usage::

        from domain.dto.backup_file import BackupFileDTO
        from views.widgets.backup.backup_review_dialog import BackupReviewDialog

        files = [BackupFileDTO(path="C:/...", name="photo.jpg", size_bytes=3_000_000, mtime=1_700_000_000_000)]
        dlg = BackupReviewDialog(files, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            decisions = dlg.get_decisions()   # {"C:/.../photo.jpg": "keep"}

    Args:
        files: List of :class:`~domain.dto.backup_file.BackupFileDTO` descriptors
            to present for review.  ``mtime`` (Unix-ms) is used for the
            "modified" date label; pass ``0`` to show ``"—"``.
        parent: Optional Qt parent widget.
    """

    def __init__(
            self,
            files: list[BackupFileDTO],
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # Only image files are shown — non-images are silently dropped.
        self._files: list[BackupFileDTO] = [
            f for f in files if file_ext(f.name) in IMAGE_EXTS
        ]
        self._rows: list[_BackupFileRow] = []

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_decisions(self) -> dict[str, str]:
        """Return ``{file_path: decision}`` for every row that has been decided.

        Rows still in ``"pending"`` state are excluded.

        Returns:
            Example: ``{"C:/backup/photo.jpg": "keep", "C:/backup/old.jpg": "delete"}``
        """
        return {
            row.file_path: row.decision
            for row in self._rows
            if row.decision != "pending"
        }

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("BackupReviewDialog")
        self.setWindowTitle("SyncDose — Review Backup Files")
        self.setMinimumWidth(_DIALOG_MIN_WIDTH)
        self.setMinimumHeight(_DIALOG_MIN_HEIGHT)
        self.setMaximumHeight(_DIALOG_MAX_HEIGHT)
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        self._header:        QWidget     = self._create_header()
        self._scroll_area:   QScrollArea = self._create_scroll_area()
        self._summary_label: QLabel      = self._create_summary_label()
        self._cancel_btn:    QPushButton = self._create_cancel_button()
        self._apply_btn:     QPushButton = self._create_apply_button()

    def _create_header(self) -> QWidget:
        # Build the icon + title + subtitle header bar.
        container = QWidget()
        container.setObjectName("BackupReviewHeader")

        icon = QLabel("⊟")
        icon.setObjectName("HeaderIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(40, 40)

        title = QLabel("Review Backup Files")
        title.setObjectName("HeaderTitle")

        subtitle = QLabel(
            f"Approve which of the {len(self._files)} "
            f"image{'s' if len(self._files) != 1 else ''} to keep or delete."
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

    def _create_scroll_area(self) -> QScrollArea:
        # Build the scrollable file list, creating one _BackupFileRow per file.
        content = QWidget()
        content.setObjectName("ScrollContent")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.SM)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        if self._files:
            for f in self._files:
                row = _BackupFileRow(f, parent=content)
                self._rows.append(row)
                layout.addWidget(row)
        else:
            # Zero-state: no images were passed (or all were filtered out).
            empty = QLabel("No image files to review.")
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

    def _create_summary_label(self) -> QLabel:
        lbl = QLabel(self._build_summary_text())
        lbl.setObjectName("SummaryLabel")
        return lbl

    def _create_cancel_button(self) -> QPushButton:
        btn = QPushButton("Cancel")
        btn.setObjectName("CancelButton")
        btn.setFixedHeight(36)
        btn.setFixedWidth(90)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _create_apply_button(self) -> QPushButton:
        btn = QPushButton("Apply Decisions")
        btn.setObjectName("ApplyButton")
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _setup_layout(self) -> None:
        # Root: header | divider | scroll area | divider | footer
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        root.setSpacing(Spacing.NONE)

        root.addWidget(self._header)
        root.addWidget(self._create_h_divider())
        root.addWidget(self._scroll_area, 1)
        root.addWidget(self._create_h_divider())
        root.addLayout(self._create_footer_layout())

    @staticmethod
    def _create_h_divider() -> QFrame:
        line = QFrame()
        line.setObjectName("BackupDivider")
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setFixedHeight(1)
        return line

    def _create_footer_layout(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(Spacing.XXL, Spacing.MD, Spacing.XXL, Spacing.LG)
        footer.setSpacing(Spacing.SM)
        footer.addWidget(self._summary_label, 1)
        footer.addWidget(self._cancel_btn)
        footer.addWidget(self._apply_btn)
        return footer

    # ── Summary helpers ───────────────────────────────────────────────────────

    def _build_summary_text(self) -> str:
        total   = len(self._rows)
        keep    = sum(1 for r in self._rows if r.decision == "keep")
        delete  = sum(1 for r in self._rows if r.decision == "delete")
        pending = total - keep - delete
        parts: list[str] = [f"{total} file{'s' if total != 1 else ''}"]
        if keep:    parts.append(f"{keep} to keep")
        if delete:  parts.append(f"{delete} to delete")
        if pending: parts.append(f"{pending} undecided")
        return "  ·  ".join(parts)

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        qss = load_stylesheet(
            BackupStyles.REVIEW,
            themed([BackupReviewColors], [LightBackupReviewColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    # ── Signals ───────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._apply_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)
        theme_manager.theme_changed.connect(self._apply_style)
        for row in self._rows:
            row.decision_changed.connect(self._on_decision_changed)

    @Slot(str)
    def _on_decision_changed(self, _: str) -> None:
        # Refresh the footer summary whenever any row decision flips.
        self._summary_label.setText(self._build_summary_text())


# ── Standalone preview ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import resources_qrc  # noqa: F401 — registers Qt virtual paths

    # Mix of images and non-images — non-images are silently dropped by the dialog.
    sample_files = [
        BackupFileDTO(r"C:\Users\Public\Pictures\vacation_photo.webp",
                      "vacation_photo.webp",  3_456_000, mtime=1_710_460_800_000),
        BackupFileDTO(r"C:\Users\Public\Pictures\ui_screenshot.png",
                      "ui_screenshot.png",    2_100_000, mtime=1_745_280_000_000),
        BackupFileDTO(r"C:\Users\Public\Pictures\portrait_2025.heic",
                      "portrait_2025.heic",   8_200_000, mtime=1_720_656_000_000),
        BackupFileDTO(r"C:\Users\Public\Pictures\event_banner.webp",
                      "event_banner.webp",      980_000, mtime=1_733_184_000_000),
        BackupFileDTO(r"C:\Users\Public\Pictures\document_scan.tif",
                      "document_scan.tif",   15_700_000, mtime=1_705_708_800_000),
        BackupFileDTO(r"C:\Users\Public\Pictures\app_icon.ico",
                      "app_icon.ico",            45_000, mtime=1_694_822_400_000),
        # Non-image — will be filtered out:
        BackupFileDTO(r"C:\Users\Public\Documents\quarterly_report.pdf",
                      "quarterly_report.pdf",   890_000, mtime=1_735_948_800_000),
    ]

    app = QApplication(sys.argv)
    dlg = BackupReviewDialog(sample_files)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        print("Decisions:", dlg.get_decisions())
    sys.exit(0)

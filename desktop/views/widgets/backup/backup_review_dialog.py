from __future__ import annotations

import sys
from typing import Final

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
    QListView, QPushButton, QVBoxLayout, QWidget,
)

from app.theme_manager import theme_manager
from domain.dto.backup_file import BackupFileDTO
from resources.colors import BackupReviewColors, LightBackupReviewColors
from resources.paths import BackupStyles
from resources.spacing import Spacing
from utils.file_type import IMAGE_EXTS, file_ext
from utils.styles import load_stylesheet, themed
from views.widgets.backup.backup_review_delegate import BackupFileDelegate
from views.widgets.backup.backup_review_model import BackupReviewModel, DecisionRole, make_colors

# ── Layout constants ──────────────────────────────────────────────────────────
_DIALOG_MIN_WIDTH:  Final[int] = 580
_DIALOG_MIN_HEIGHT: Final[int] = 420
_DIALOG_MAX_HEIGHT: Final[int] = 700
_LIST_SPACING:      Final[int] = 4


class BackupReviewDialog(QDialog):
    """Modal dialog for reviewing and approving backup file decisions.

    Shows a virtualised list of backup image files.  Each row has
    **✓ Keep** / **✗ Delete** toggle buttons rendered by the delegate.
    A live footer summary counts the current decisions.

    Footer buttons:

    * **Keep All** / **Cancel** — mark every remaining pending file as "keep"
      and close (``Accepted``).  Both buttons are always enabled.
    * **Apply Decisions** — commits all currently-decided rows (removes them
      from the list) and *stays open* so the user can continue reviewing the
      remaining pending files.  Enabled only when at least one row has been
      decided.  If the list empties after committing, the dialog closes
      automatically.
    * **Auto-dismiss** — fires as soon as the last visible row is decided
      (pending → 0), without requiring any button press.

    The dialog always resolves as ``Accepted``; there is no rejection path.
    The caller reads :meth:`get_decisions` to act on the result.  Decisions
    from rows committed via *Apply Decisions* mid-session are included.

    Non-image files are silently filtered out on construction.  Files still
    in ``"pending"`` state are **omitted** from :meth:`get_decisions`.

    Usage::

        from domain.dto.backup_file import BackupFileDTO
        from views.widgets.backup.backup_review_dialog import BackupReviewDialog

        files = [BackupFileDTO(path="C:/...", name="photo.jpg", size_bytes=3_000_000, mtime=...)]
        dlg = BackupReviewDialog(files, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            decisions = dlg.get_decisions()   # {"C:/.../photo.jpg": "keep"}

    Args:
        files:  List of :class:`~domain.dto.backup_file.BackupFileDTO` descriptors.
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
        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_decisions(self) -> dict[str, str]:
        """Return ``{file_path: decision}`` for every row that has been decided.

        Rows still in ``"pending"`` state are excluded.
        """
        return self._model.get_decisions()

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
        self._list_view:     QListView   = self._create_list_view()
        self._summary_label: QLabel      = self._create_summary_label()
        self._keep_all_btn:  QPushButton = self._create_keep_all_button()
        self._cancel_btn:    QPushButton = self._create_cancel_button()
        self._apply_btn:     QPushButton = self._create_apply_button()

    def _create_header(self) -> QWidget:
        container = QWidget()
        container.setObjectName("BackupReviewHeader")

        icon = QLabel("⊟")
        icon.setObjectName("HeaderIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(40, 40)

        title = QLabel("Review Backup Files")
        title.setObjectName("HeaderTitle")

        n = len(self._files)
        subtitle = QLabel(
            f"Approve which of the {n} "
            f"image{'s' if n != 1 else ''} to keep or delete."
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

    def _create_list_view(self) -> QListView:
        colors = make_colors(theme_manager.is_dark)
        self._model    = BackupReviewModel(self._files, parent=self)
        self._delegate = BackupFileDelegate(colors, parent=self)

        list_view = QListView()
        list_view.setObjectName("FileListView")
        list_view.setModel(self._model)
        list_view.setItemDelegate(self._delegate)
        list_view.setUniformItemSizes(True)
        list_view.setSpacing(_LIST_SPACING)
        list_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_view.setFrameShape(QFrame.Shape.NoFrame)
        list_view.setMouseTracking(True)
        list_view.viewport().setMouseTracking(True)

        if not self._files:
            list_view.setVisible(False)
            self._empty_label: QLabel | None = QLabel("No image files to review.")
            self._empty_label.setObjectName("EmptyLabel")
            self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self._empty_label = None

        return list_view

    def _create_summary_label(self) -> QLabel:
        lbl = QLabel(self._build_summary_text())
        lbl.setObjectName("SummaryLabel")
        return lbl

    def _create_keep_all_button(self) -> QPushButton:
        btn = QPushButton("Keep All")
        btn.setObjectName("KeepAllButton")
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

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
        btn.setEnabled(False)   # enabled only once ≥1 file has been decided
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _setup_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        root.setSpacing(Spacing.NONE)

        root.addWidget(self._header)
        root.addWidget(self._create_h_divider())

        if self._empty_label is not None:
            empty_wrap = QWidget()
            empty_wrap.setObjectName("ScrollContent")
            wl = QVBoxLayout(empty_wrap)
            wl.addWidget(self._empty_label)
            root.addWidget(empty_wrap, 1)
        else:
            root.addWidget(self._list_view, 1)

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
        footer.addWidget(self._keep_all_btn)   # bulk-keep action on the left
        footer.addWidget(self._summary_label, 1)
        footer.addWidget(self._cancel_btn)
        footer.addWidget(self._apply_btn)
        return footer

    # ── Summary ───────────────────────────────────────────────────────────────

    def _build_summary_text(self) -> str:
        if not self._files:
            return "No files"
        keep, delete, pending = self._model.decision_counts()
        total = keep + delete + pending   # live count — shrinks as Apply commits rows
        if total == 0:
            return "All files processed"
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
        self._delegate.update_colors(make_colors(theme_manager.is_dark))
        self._list_view.viewport().update()

    # ── Signals ───────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        # Apply commits decided rows and stays open; Keep All / Cancel both keep-all and close.
        self._apply_btn.clicked.connect(self._on_apply_clicked)
        self._cancel_btn.clicked.connect(self._on_keep_all_clicked)
        self._keep_all_btn.clicked.connect(self._on_keep_all_clicked)
        theme_manager.theme_changed.connect(self._apply_style)
        self._model.dataChanged.connect(self._on_decision_changed)

    @Slot()
    def _on_apply_clicked(self) -> None:
        """Commit decided rows (remove from list) and stay open.

        If no rows remain after committing, the dialog auto-accepts.
        """
        self._model.apply_decided()
        self._summary_label.setText(self._build_summary_text())
        keep, delete, _ = self._model.decision_counts()
        self._apply_btn.setEnabled((keep + delete) > 0)
        if self._model.rowCount() == 0:
            self.accept()

    @Slot()
    def _on_keep_all_clicked(self) -> None:
        """Mark every remaining pending file as 'keep'.

        Triggers _on_decision_changed for each row; auto-dismiss fires when
        the last pending row is flipped (pending → 0).
        """
        for row in range(self._model.rowCount()):
            if self._model.data(self._model.index(row), DecisionRole) == "pending":
                self._model.set_decision(row, "keep")

    @Slot()
    def _on_decision_changed(self, *_) -> None:
        self._summary_label.setText(self._build_summary_text())
        keep, delete, pending = self._model.decision_counts()
        self._apply_btn.setEnabled((keep + delete) > 0)
        # Auto-dismiss once every visible row has a decision.
        if pending == 0 and self._model.rowCount() > 0:
            self.accept()


# ── Standalone preview ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import resources_qrc  # noqa: F401

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

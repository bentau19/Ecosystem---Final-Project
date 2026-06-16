from __future__ import annotations

import sys
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from app.theme_manager import theme_manager
from domain.dto.backup_review_prompt import BackupReviewPromptDTO
from resources.colors import (
    BackupClassificationReviewColors, LightBackupClassificationReviewColors,
)
from resources.paths import BackupStyles
from resources.spacing import Spacing
from utils.file_type import IMAGE_EXTS, file_ext
from utils.styles import load_stylesheet, themed
from views.widgets.backup.helpers import load_thumb

# ── Layout constants ──────────────────────────────────────────────────────────
_DIALOG_WIDTH:  Final[int] = 420
_THUMB_SIZE:    Final[int] = 96
_BUTTON_HEIGHT: Final[int] = 38


class BackupClassificationReviewDialog(QDialog):
    """Modal dialog asking the user to keep or remove a flagged file.

    Shown when the ML image classifier's argmax favours "remove" but isn't
    confident enough to act automatically
    (:attr:`~classifer.ScreeningResult.NEEDS_REVIEW`). Presents a thumbnail
    preview of the file and asks the user to **Keep** or **Remove** it.

    Resolves as ``Accepted`` if the user clicks **Keep**, or ``Rejected`` if
    the user clicks **Remove** or closes the dialog.  Any non-rejected result
    should be treated as *keep* by the caller.

    Usage::

        from domain.dto.backup_review_prompt import BackupReviewPromptDTO
        from views.widgets.backup.backup_classification_review_dialog import (
            BackupClassificationReviewDialog,
        )

        prompt = BackupReviewPromptDTO(
            channel="backup_slot_meta_0",
            file_name="photo.jpg",
            cache_path="C:/Temp/SyncDose_backup_xyz/abc123.tmp",
            confidence=0.78,
        )
        dlg = BackupClassificationReviewDialog(prompt, parent=self)
        keep = dlg.exec() != QDialog.DialogCode.Rejected
        backup_vm.resolve_review(prompt.channel, keep)

    Args:
        prompt: Describes the file pending review.
        parent: Optional Qt parent widget.
    """

    def __init__(
            self,
            prompt: BackupReviewPromptDTO,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._prompt: BackupReviewPromptDTO = prompt

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("BackupClassificationReviewDialog")
        self.setWindowTitle("SyncDose — Review File")
        self.setFixedWidth(_DIALOG_WIDTH)
        self.setModal(True)
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        self._header:      QWidget     = self._create_header()
        self._preview_row: QWidget     = self._create_preview_row()
        self._keep_btn:    QPushButton = self._create_keep_button()
        self._remove_btn:  QPushButton = self._create_remove_button()

    def _create_header(self) -> QWidget:
        # Build the icon + title + confidence subtitle header bar.
        container = QWidget()
        container.setObjectName("ReviewHeader")

        icon = QLabel("⚠")
        icon.setObjectName("HeaderIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(40, 40)

        title = QLabel("Review This File?")
        title.setObjectName("HeaderTitle")

        pct = round(self._prompt.confidence * 100)
        subtitle = QLabel(f"Our content filter is {pct}% sure this file is unwanted")
        subtitle.setObjectName("HeaderSubtitle")
        subtitle.setWordWrap(True)

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

    def _create_preview_row(self) -> QWidget:
        # Build the thumbnail + filename row.
        container = QWidget()
        container.setObjectName("PreviewRow")

        thumb = self._create_thumb_label()

        name = QLabel(self._prompt.file_name)
        name.setObjectName("FileName")
        name.setWordWrap(True)

        meta = QLabel("Choose Keep to save it anyway, or Remove to discard it.")
        meta.setObjectName("FileMeta")
        meta.setWordWrap(True)

        text_col = QVBoxLayout()
        text_col.setSpacing(Spacing.XS)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.addWidget(name)
        text_col.addWidget(meta)

        row = QHBoxLayout(container)
        row.setContentsMargins(Spacing.XXL, Spacing.MD, Spacing.XXL, Spacing.MD)
        row.setSpacing(Spacing.MD)
        row.addWidget(thumb, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(text_col, 1)
        return container

    def _create_thumb_label(self) -> QLabel:
        # Load the file thumbnail; fall back to a cyan "IMG" circle if unreadable.
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)

        pixmap = None
        if file_ext(self._prompt.file_name) in IMAGE_EXTS:
            pixmap = load_thumb(self._prompt.cache_path, _THUMB_SIZE)

        if pixmap is not None:
            lbl.setObjectName("FileThumb")
            lbl.setPixmap(pixmap)
        else:
            lbl.setObjectName("FileThumbFallback")
            lbl.setText("FILE")

        return lbl

    def _create_keep_button(self) -> QPushButton:
        btn = QPushButton("✓  Keep")
        btn.setObjectName("KeepButton")
        btn.setFixedHeight(_BUTTON_HEIGHT)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _create_remove_button(self) -> QPushButton:
        btn = QPushButton("✗  Remove")
        btn.setObjectName("RemoveButton")
        btn.setFixedHeight(_BUTTON_HEIGHT)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _setup_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        root.setSpacing(Spacing.NONE)

        root.addWidget(self._header)
        root.addWidget(self._make_divider())
        root.addWidget(self._preview_row)
        root.addWidget(self._make_divider())
        root.addLayout(self._make_footer())

    @staticmethod
    def _make_divider() -> QFrame:
        line = QFrame()
        line.setObjectName("ReviewDivider")
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setFixedHeight(1)
        return line

    def _make_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(Spacing.XXL, Spacing.MD, Spacing.XXL, Spacing.LG)
        footer.setSpacing(Spacing.SM)
        footer.addStretch(1)
        footer.addWidget(self._remove_btn)
        footer.addWidget(self._keep_btn)
        return footer

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        qss = load_stylesheet(
            BackupStyles.CLASSIFICATION_REVIEW,
            themed(
                [BackupClassificationReviewColors],
                [LightBackupClassificationReviewColors],
                theme_manager.is_dark,
            ),
        )
        self.setStyleSheet(qss)

    # ── Signals ───────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._keep_btn.clicked.connect(self.accept)
        self._remove_btn.clicked.connect(self.reject)
        theme_manager.theme_changed.connect(self._apply_style)


# ── Standalone preview ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import resources_qrc  # noqa: F401 — registers Qt virtual paths

    app = QApplication(sys.argv)
    sample = BackupReviewPromptDTO(
        channel="backup_slot_meta_0",
        file_name="suspicious_photo.jpg",
        cache_path=r"C:\does\not\exist.tmp",
        confidence=0.78,
    )
    dlg = BackupClassificationReviewDialog(sample)
    result = dlg.exec()
    label = "Keep" if result != QDialog.DialogCode.Rejected else "Remove"
    print(label)
    sys.exit(0)

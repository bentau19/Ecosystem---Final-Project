from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from app.theme_manager import theme_manager
from resources.colors import LightPalette, Palette
from resources.spacing import Spacing
from utils.file_type import fmt_size

# ── Layout constants ──────────────────────────────────────────────────────────
_DIALOG_WIDTH: int = 500


def _build_qss(is_dark: bool) -> str:
    """Return the dialog QSS with colors resolved for the active theme.

    Args:
        is_dark: Whether the dark color palette should be used.

    Returns:
        A QSS stylesheet string with theme-appropriate colors interpolated.
    """
    p = Palette if is_dark else LightPalette
    cyan = Palette.CYAN_400   # accent — invariant across themes

    return f"""
    QDialog#BackupDestPickerDialog {{
        background-color: {p.DARK_900};
        color: {p.SLATE_100};
    }}

    /* ── Header ─────────────────────────────────────────────────────── */
    QWidget#DestHeader {{
        background-color: {p.DARK_800};
    }}
    QLabel#DestHeaderIcon {{
        font-size: 22px;
    }}
    QLabel#DestHeaderTitle {{
        color: {p.SLATE_100};
        font-size: 14px;
        font-weight: 600;
    }}
    QLabel#DestHeaderSubtitle {{
        color: {p.SLATE_500};
        font-size: 12px;
    }}

    /* ── Divider ─────────────────────────────────────────────────────── */
    QFrame#DestDivider {{
        background-color: {p.GRAY_700};
    }}

    /* ── Body ────────────────────────────────────────────────────────── */
    QLabel#DestFolderLabel {{
        color: {p.SLATE_500};
        font-size: 11px;
        font-weight: 500;
    }}
    QLineEdit#DestPathInput {{
        background-color: {p.DARK_750};
        border: 1px solid {p.GRAY_700};
        border-radius: 4px;
        color: {p.SLATE_100};
        padding: 4px 8px;
        font-size: 12px;
    }}
    QLineEdit#DestPathInput:focus {{
        border-color: {cyan};
    }}

    /* ── Browse button (secondary) ───────────────────────────────────── */
    QPushButton#BrowseButton {{
        background-color: {p.DARK_750};
        border: 1px solid {p.GRAY_700};
        border-radius: 4px;
        color: {cyan};
        font-size: 12px;
        font-weight: 500;
        padding: 4px 12px;
    }}
    QPushButton#BrowseButton:hover {{
        background-color: {p.DARK_720};
        border-color: {cyan};
    }}
    QPushButton#BrowseButton:pressed {{
        background-color: {p.DARK_800};
    }}

    /* ── Cancel button (ghost) ───────────────────────────────────────── */
    QPushButton#CancelButton {{
        background-color: transparent;
        border: 1px solid {p.GRAY_700};
        border-radius: 4px;
        color: {p.SLATE_500};
        font-size: 12px;
        padding: 4px 14px;
    }}
    QPushButton#CancelButton:hover {{
        border-color: {p.SLATE_500};
        color: {p.SLATE_100};
    }}
    QPushButton#CancelButton:pressed {{
        background-color: {p.DARK_750};
    }}

    /* ── Confirm button (primary accent) ─────────────────────────────── */
    QPushButton#ConfirmButton {{
        background-color: {cyan};
        border: none;
        border-radius: 4px;
        color: {Palette.DARK_900};
        font-size: 12px;
        font-weight: 600;
        padding: 4px 18px;
    }}
    QPushButton#ConfirmButton:hover {{
        background-color: {Palette.TEAL_400};
    }}
    QPushButton#ConfirmButton:pressed {{
        background-color: {Palette.TEAL_700};
    }}
    QPushButton#ConfirmButton:disabled {{
        background-color: {p.GRAY_700};
        color: {p.SLATE_600};
    }}
    """


class BackupDestPickerDialog(QDialog):
    """Modal folder-picker for selecting a backup destination.

    Displays the file count and total size from the incoming manifest so the
    user understands what they are about to receive, then lets them browse for
    a local destination folder.

    Usage::

        dlg = BackupDestPickerDialog(file_count=42, total_bytes=1_234_567_890, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vm.confirm_dest_dir(dlg.selected_path)
        else:
            vm.cancel_dest_selection()

    Args:
        file_count:  Number of files in the backup manifest.
        total_bytes: Combined byte size of all files.
        parent:      Optional Qt parent widget.
    """

    def __init__(
            self,
            file_count: int,
            total_bytes: int,
            storage_saver: bool = False,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._file_count: int = file_count
        self._total_bytes: int = total_bytes
        self._storage_saver: bool = storage_saver
        self._selected_path: str = ""

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def selected_path(self) -> str:
        """Get the absolute path the user chose.

        Returns:
            The selected destination folder path, or an empty string if the
            user has not yet chosen a folder.
        """
        return self._selected_path

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("BackupDestPickerDialog")
        # Surface above all other apps so an incoming backup request is never missed.
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("SyncDose — Choose Backup Destination")
        self.setFixedWidth(_DIALOG_WIDTH)
        # Let Qt size the height from content; prevent the user from resizing.
        self.setSizeGripEnabled(False)
        self._create_widgets()
        self._setup_layout()
        # Lock height to the natural content size after layout is finalised.
        self.layout().setSizeConstraint(
            self.layout().SizeConstraint.SetFixedSize
        )

    def _create_widgets(self) -> None:
        self._header: QWidget = self._create_header()
        self._path_input: QLineEdit = self._create_path_input()
        self._browse_btn: QPushButton = self._create_browse_button()
        self._cancel_btn: QPushButton = self._create_cancel_button()
        self._confirm_btn: QPushButton = self._create_confirm_button()

    def _create_header(self) -> QWidget:
        # Build the icon + title + subtitle header bar.
        container = QWidget()
        container.setObjectName("DestHeader")

        icon = QLabel("📥")
        icon.setObjectName("DestHeaderIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(40, 40)

        n = self._file_count
        title = QLabel("Incoming Backup")
        title.setObjectName("DestHeaderTitle")

        size_str = (
            f"Up to {fmt_size(self._total_bytes)}  ·  Storage Saver on"
            if self._storage_saver
            else fmt_size(self._total_bytes)
        )
        subtitle = QLabel(
            f"{n} file{'s' if n != 1 else ''}  ·  "
            f"{size_str} — choose a destination folder"
        )
        subtitle.setObjectName("DestHeaderSubtitle")

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

    @staticmethod
    def _create_path_input() -> QLineEdit:
        inp = QLineEdit()
        inp.setObjectName("DestPathInput")
        inp.setReadOnly(True)
        inp.setPlaceholderText("No folder selected…")
        return inp

    @staticmethod
    def _create_browse_button() -> QPushButton:
        btn = QPushButton("Browse…")
        btn.setObjectName("BrowseButton")
        btn.setFixedHeight(32)
        btn.setMinimumWidth(80)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    @staticmethod
    def _create_cancel_button() -> QPushButton:
        btn = QPushButton("Cancel")
        btn.setObjectName("CancelButton")
        btn.setFixedHeight(36)
        btn.setMinimumWidth(80)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    @staticmethod
    def _create_confirm_button() -> QPushButton:
        btn = QPushButton("Start Backup")
        btn.setObjectName("ConfirmButton")
        btn.setFixedHeight(36)
        btn.setEnabled(False)   # disabled until a path is chosen
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _setup_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        root.setSpacing(Spacing.NONE)

        root.addWidget(self._header)
        root.addWidget(self._make_divider())
        root.addLayout(self._make_body_layout())
        root.addWidget(self._make_divider())
        root.addLayout(self._make_footer_layout())

    @staticmethod
    def _make_divider() -> QFrame:
        line = QFrame()
        line.setObjectName("DestDivider")
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setFixedHeight(1)
        return line

    def _make_body_layout(self) -> QVBoxLayout:
        # Folder-label stacked above the path-input + browse row.
        folder_label = QLabel("Save to folder:")
        folder_label.setObjectName("DestFolderLabel")

        path_row = QHBoxLayout()
        path_row.setSpacing(Spacing.SM)
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.addWidget(self._path_input, 1)
        path_row.addWidget(self._browse_btn, 0)

        body = QVBoxLayout()
        body.setContentsMargins(Spacing.XXL, Spacing.MD, Spacing.XXL, Spacing.MD)
        body.setSpacing(Spacing.SM)
        body.addWidget(folder_label)
        body.addLayout(path_row)
        return body

    def _make_footer_layout(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(Spacing.XXL, Spacing.MD, Spacing.XXL, Spacing.LG)
        footer.setSpacing(Spacing.SM)
        footer.addStretch(1)
        footer.addWidget(self._cancel_btn)
        footer.addWidget(self._confirm_btn)
        return footer

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        self.setStyleSheet(_build_qss(theme_manager.is_dark))

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._browse_btn.clicked.connect(self._on_browse_clicked)
        self._confirm_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)
        theme_manager.theme_changed.connect(self._apply_style)

    @Slot()
    def _on_browse_clicked(self) -> None:
        # Open the native folder picker and populate the path input.
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose Backup Destination",
            self._selected_path or "",
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        if folder:
            self._selected_path = folder
            self._path_input.setText(folder)
            self._confirm_btn.setEnabled(True)


# ── Standalone preview ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    import resources_qrc  # noqa: F401 — registers Qt virtual paths

    app = QApplication(sys.argv)
    dlg = BackupDestPickerDialog(file_count=42, total_bytes=1_234_567_890, storage_saver=True)
    result = dlg.exec()
    if result == QDialog.DialogCode.Accepted:
        print(f"Accepted — path: {dlg.selected_path}")
    else:
        print("Cancelled")
    sys.exit(0)

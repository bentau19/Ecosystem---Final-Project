"""
File-received toast notification widget.

A frameless, always-on-top banner that appears at the top-center of the
primary screen and stays visible until the user acts.  The user either picks
a save location (triggering :meth:`~viewmodels.file_transfer.FileTransferViewModel.receive_file`)
or cancels (triggering :meth:`~viewmodels.file_transfer.FileTransferViewModel.reject_receive`).

Intentionally **app-state-aware** only through ``app_state.file_transfer_viewmodel``
so the widget stays decoupled from service internals.
"""
import platform
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QParallelAnimationGroup, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel,
    QPushButton, QWidget, QFileDialog,
)

from app.app_state import app_state
from resources.colors import FileReceivedToastColors
from resources.paths import ToastStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet
from viewmodels.file_transfer import FileTransferViewModel

# Minimum width for the toast banner — expands to fit longer filenames.
_TOAST_MIN_WIDTH: int = 480
# Diameter of the icon circle in pixels.
_ICON_SIZE: int = 32
# Distance from the top edge of the available screen area.
_SCREEN_MARGIN: int = 20


def _play_notification_sound() -> None:
    """Play the OS notification sound in a non-blocking, cross-platform way.

    - **Windows** — plays the ``SystemNotification`` alias via ``winsound``.
    - **macOS** — plays ``Glass.aiff`` via ``afplay`` in a detached subprocess.
    - **Linux / other** — tries ``paplay``; falls back to :meth:`QApplication.beep`.
    """
    system = platform.system()
    if system == "Windows":
        import winsound  # stdlib on Windows only — import guarded intentionally
        winsound.PlaySound("SystemNotification", winsound.SND_ALIAS | winsound.SND_ASYNC)
    elif system == "Darwin":
        subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
    else:
        try:
            subprocess.Popen(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga"]
            )
        except FileNotFoundError:
            QApplication.beep()


class FileReceivedToast(QWidget):
    """Frameless top-center banner shown when a file arrives from the phone.

    All content sits in a single horizontal row::

        [↓]  File Received  ·  filename.pdf   [Download file]  [Cancel download]

    Clicking **Download file** opens a save-location dialog; on confirmation
    :meth:`~viewmodels.file_transfer.FileTransferViewModel.receive_file` is
    called.  Clicking **Cancel download** (or closing the dialog without saving)
    calls :meth:`~viewmodels.file_transfer.FileTransferViewModel.reject_receive`.

    Args:
        filename: Name of the incoming file shown in the toast body.
        file_size: Byte count of the incoming file, forwarded to
            :meth:`~viewmodels.file_transfer.FileTransferViewModel.receive_file`
            on acceptance.
        parent: Optional Qt parent widget (usually ``None`` for a top-level toast).
    """

    def __init__(
            self,
            filename: str,
            file_size: int,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._filename: str = filename
        self._file_size: int = file_size

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("FileReceivedToast")
        self.setMinimumWidth(_TOAST_MIN_WIDTH)
        self._closing: bool = False

        self._file_transfer_vm: FileTransferViewModel = app_state.file_transfer_viewmodel

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── Public API ────────────────────────────────────────────────────────────

    def show_toast(self) -> None:
        """Position at the top-center of the primary screen and show.

        Caps the widget at 70 % of the screen width so long filenames never
        produce a banner that spans the full monitor.
        """
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.setMaximumWidth(int(geo.width() * 0.70))
        self.adjustSize()
        x = geo.left() + (geo.width() - self.width()) // 2
        y = geo.top() + _SCREEN_MARGIN
        self.move(x, y)
        _play_notification_sound()
        self.show()
        self.raise_()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        """Create all child widgets and arrange them in the layout."""
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        """Instantiate and store all child widgets."""
        self._icon_circle: QLabel = self._create_icon_circle()
        self._title_label: QLabel = self._create_title_label()
        self._separator_dot: QLabel = self._create_separator_dot()
        self._filename_label: QLabel = self._create_filename_label()
        self._download_button: QPushButton = self._create_download_button()
        self._cancel_button: QPushButton = self._create_cancel_button()

    @staticmethod
    def _create_icon_circle() -> QLabel:
        """Return the fixed-size circle label containing the download arrow."""
        lbl = QLabel("↓")
        lbl.setObjectName("IconCircle")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        return lbl

    @staticmethod
    def _create_title_label() -> QLabel:
        """Return the "File Received" heading label."""
        lbl = QLabel("File Received")
        lbl.setObjectName("TitleLabel")
        return lbl

    @staticmethod
    def _create_separator_dot() -> QLabel:
        """Return the muted mid-dot separator between title and filename."""
        lbl = QLabel("·")
        lbl.setObjectName("SeparatorDot")
        return lbl

    def _create_filename_label(self) -> QLabel:
        """Return the filename label with a tooltip for clipped text."""
        lbl = QLabel(self._filename)
        lbl.setObjectName("FilenameLabel")
        lbl.setToolTip(self._filename)
        return lbl

    @staticmethod
    def _create_download_button() -> QPushButton:
        """Return the primary "Download file" text-link button."""
        btn = QPushButton("Download file")
        btn.setObjectName("DownloadButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)
        return btn

    @staticmethod
    def _create_cancel_button() -> QPushButton:
        """Return the secondary "Cancel download" text-link button."""
        btn = QPushButton("Cancel download")
        btn.setObjectName("CancelButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)
        return btn

    def _setup_layout(self) -> None:
        """Arrange all child widgets in a single horizontal banner row."""
        root = QHBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        root.setSpacing(Spacing.SM)

        root.addWidget(self._icon_circle, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(self._title_label, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(self._separator_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(self._filename_label, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addStretch()
        root.addWidget(self._download_button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(self._cancel_button, 0, Qt.AlignmentFlag.AlignVCenter)

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        """Load and apply the toast QSS via the Qt resource filesystem."""
        qss = load_stylesheet(ToastStyles.FILE_RECEIVED, [FileReceivedToastColors])
        self.setStyleSheet(qss)

    # ── Signals ───────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        """Wire button clicks and viewmodel signals to their slots."""
        self._download_button.clicked.connect(self._on_download_requested)
        self._cancel_button.clicked.connect(self._on_cancel_requested)
        self._cancel_button.clicked.connect(self._close_with_animation)
        self._file_transfer_vm.receive_error.connect(self.close)

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot()
    def _on_download_requested(self) -> None:
        """Open a save-location dialog; accept or reject based on the result.

        If the user picks a path, calls
        :meth:`~viewmodels.file_transfer.FileTransferViewModel.receive_file`
        and then closes the toast with an animation.  If the user cancels the
        dialog, calls
        :meth:`~viewmodels.file_transfer.FileTransferViewModel.reject_receive`
        and closes the toast — the transfer is abandoned.
        """
        default_path: Path = Path.home() / "Desktop" / self._filename
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save File",
            str(default_path),
            "All Files (*)",
        )
        if dest_path:
            self._file_transfer_vm.receive_file(dest_path, self._file_size)
        else:
            self._file_transfer_vm.reject_receive()

        self._close_with_animation()

    @Slot()
    def _on_cancel_requested(self) -> None:
        """Reject the incoming transfer when the user clicks Cancel."""
        self._file_transfer_vm.reject_receive()

    @Slot()
    def _close_with_animation(self) -> None:
        """Fade-and-slide the toast upward, then destroy it.

        Runs a 250 ms :class:`QParallelAnimationGroup` that simultaneously
        fades ``windowOpacity`` from 1.0 → 0.0 and drifts the widget 16 px
        upward.  The :meth:`close` call is deferred until the animation
        finishes so the widget is never torn down mid-frame.
        """
        if self._closing:
            return
        self._closing = True

        group = QParallelAnimationGroup(self)

        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(250)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.Type.InCubic)

        slide = QPropertyAnimation(self, b"pos", self)
        slide.setDuration(250)
        slide.setStartValue(self.pos())
        slide.setEndValue(self.pos() - QPoint(0, 16))
        slide.setEasingCurve(QEasingCurve.Type.InCubic)

        group.addAnimation(fade)
        group.addAnimation(slide)
        group.finished.connect(self.close)
        group.start()


# ── Standalone preview ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import resources_qrc  # noqa: F401 — registers Qt virtual paths

    app = QApplication(sys.argv)
    toast = FileReceivedToast("quarterly_report_Q1_2026_final.pdf", 2_048_000)
    toast.show_toast()
    sys.exit(app.exec())

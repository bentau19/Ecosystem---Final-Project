"""
File handler entry point.

Standalone Windows process launched by the OS when the user invokes the
"Send with SyncDose" shell context-menu action.  Receives the target file
path as ``sys.argv[1]``, writes it to the SyncDose named pipe, and exits.

If the pipe is not found (main app not running or phone not connected) a
:class:`PhoneNotDetectedDialog` is shown.  Any other failure shows a
:class:`TransferErrorDialog`.

Because this module is compiled to its own executable via PyInstaller it has
no access to the main app's Qt resource virtual filesystem (``resources_qrc``).
All styles are therefore applied as inline QSS strings using the project's
design-token constants from ``resources/colors.py`` and
``resources/spacing.py``.
"""
import sys
from typing import Final

import pywintypes
import win32file
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from resources.colors import Palette
from resources.spacing import Spacing

# ── Constants ──────────────────────────────────────────────────────────────────

PIPE_NAME: Final[str] = r'\\.\pipe\FileSend'

# Windows error code returned by CreateFile when the named pipe server is not
# listening (i.e. SyncDose is not running or the phone is not connected).
_WINERROR_PIPE_NOT_FOUND: Final[int] = 2  # ERROR_FILE_NOT_FOUND


# ── Shared dialog base ─────────────────────────────────────────────────────────

class _BaseHandlerDialog(QDialog):
    """Dark-themed notification dialog base for file-handler error states.

    Renders a colored icon strip, a bold heading, an explanatory body
    message, and a single dismiss button.  Sub-classes supply the accent
    color, icon character, title, and message — everything else is shared.

    Args:
        accent: Six-digit hex colour string (e.g. ``"#FF9800"``) applied to
            the icon strip background tint, strip text, and dismiss button.
        icon_char: Emoji or single character rendered inside the icon strip.
        title: Short, bold heading displayed below the strip.
        message: One-to-two sentence body text that guides the user.
        parent: Optional Qt parent widget.
    """

    _DIALOG_WIDTH: Final[int] = 380
    _STRIP_HEIGHT: Final[int] = 72
    _BUTTON_HEIGHT: Final[int] = 36
    _BORDER_RADIUS: Final[int] = 12
    _BUTTON_RADIUS: Final[int] = 6
    _TITLE_FONT_SIZE: Final[int] = 15
    _BODY_FONT_SIZE: Final[int] = 13
    _ICON_FONT_SIZE: Final[int] = 28

    def __init__(
        self,
        accent: str,
        icon_char: str,
        title: str,
        message: str,
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        self._accent: str = accent
        self._icon_char: str = icon_char
        self._title: str = title
        self._message: str = message
        self._setup_ui()
        self._setup_style()

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        """Build the widget hierarchy and configure window properties."""
        self.setObjectName("HandlerDialog")
        self.setWindowTitle("SyncDose")
        self.setFixedWidth(self._DIALOG_WIDTH)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
        )

        root: QVBoxLayout = QVBoxLayout(self)
        root.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.XXL)
        root.setSpacing(Spacing.NONE)

        root.addWidget(self._create_icon_strip())
        root.addSpacing(Spacing.XL)

        body: QVBoxLayout = QVBoxLayout()
        body.setContentsMargins(Spacing.XXL, Spacing.NONE, Spacing.XXL, Spacing.NONE)
        body.setSpacing(Spacing.NONE)

        body.addWidget(self._create_title_label())
        body.addSpacing(Spacing.SM)
        body.addWidget(self._create_message_label())
        body.addSpacing(Spacing.XL)
        body.addWidget(self._create_dismiss_button())

        root.addLayout(body)

    def _create_icon_strip(self) -> QLabel:
        """Return the accent-coloured strip containing the icon character.

        Returns:
            A :class:`QLabel` fixed to :attr:`_STRIP_HEIGHT` pixels tall,
            centred, with a subtle tinted background derived from the accent.
        """
        strip: QLabel = QLabel(self._icon_char)
        strip.setObjectName("IconStrip")
        strip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        strip.setFixedHeight(self._STRIP_HEIGHT)
        return strip

    def _create_title_label(self) -> QLabel:
        """Return the bold heading label.

        Returns:
            A centred, word-wrapped :class:`QLabel` with the dialog title.
        """
        label: QLabel = QLabel(self._title)
        label.setObjectName("TitleLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _create_message_label(self) -> QLabel:
        """Return the explanatory body-text label.

        Returns:
            A centred, word-wrapped :class:`QLabel` with the body message.
        """
        label: QLabel = QLabel(self._message)
        label.setObjectName("MessageLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _create_dismiss_button(self) -> QPushButton:
        """Return the dismiss button wired to :meth:`accept`.

        Returns:
            A full-width :class:`QPushButton` labelled **OK** that closes
            the dialog when clicked.
        """
        btn: QPushButton = QPushButton("OK")
        btn.setObjectName("DismissButton")
        btn.setFixedHeight(self._BUTTON_HEIGHT)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.accept)
        return btn

    # ── Styling ────────────────────────────────────────────────────────────────

    def _setup_style(self) -> None:
        """Apply inline QSS using the project's design-token constants.

        Inline styles are used (rather than a loaded ``.qss`` file) because
        this module runs as a standalone executable that has no access to the
        main app's Qt virtual resource filesystem.
        """
        # Append "22" (≈ 13 % opacity) to the six-digit accent hex to produce
        # an eight-digit RGBA hex for the subtle icon-strip background tint.
        strip_bg: str = f"{self._accent}22"

        self.setStyleSheet(f"""
            QDialog#HandlerDialog {{
                background-color: {Palette.DARK_900};
                border: 1px solid {Palette.GRAY_700};
                border-radius: {self._BORDER_RADIUS}px;
            }}
            QLabel#IconStrip {{
                background-color: {strip_bg};
                color: {self._accent};
                font-size: {self._ICON_FONT_SIZE}px;
                border-bottom: 1px solid {Palette.GRAY_700};
            }}
            QLabel#TitleLabel {{
                color: {Palette.SLATE_100};
                font-size: {self._TITLE_FONT_SIZE}px;
                font-weight: 600;
            }}
            QLabel#MessageLabel {{
                color: {Palette.SLATE_500};
                font-size: {self._BODY_FONT_SIZE}px;
            }}
            QPushButton#DismissButton {{
                background-color: {self._accent};
                color: {Palette.DARK_900};
                border: none;
                border-radius: {self._BUTTON_RADIUS}px;
                font-size: {self._BODY_FONT_SIZE}px;
                font-weight: 600;
            }}
            QPushButton#DismissButton:hover {{
                background-color: {self._accent}CC;
            }}
            QPushButton#DismissButton:pressed {{
                background-color: {self._accent}99;
            }}
        """)


# ── Concrete dialogs ───────────────────────────────────────────────────────────

class PhoneNotDetectedDialog(_BaseHandlerDialog):
    """Shown when the SyncDose named pipe is not open.

    This means either the main app is not running or the phone is not yet
    connected.  The dialog guides the user to open SyncDose, connect their
    phone, and retry.
    """

    def __init__(self, parent: QDialog | None = None) -> None:
        """Initialize the dialog with the phone-not-detected copy and styling."""
        super().__init__(
            accent=Palette.ORANGE_500,
            icon_char="📵",
            title="Phone Not Detected",
            message=(
                "Make sure SyncDose is open and your phone is connected, "
                "then try again."
            ),
            parent=parent,
        )


class TransferErrorDialog(_BaseHandlerDialog):
    """Shown when an unexpected error occurs while writing to the named pipe.

    Covers all failure modes other than a missing pipe (e.g. broken handle,
    access-denied, encoding errors).
    """

    def __init__(self, parent: QDialog | None = None) -> None:
        """Initialize the dialog with the generic-error copy and styling."""
        super().__init__(
            accent=Palette.PINK_500,
            icon_char="⚠️",
            title="An Error Occurred",
            message="Something went wrong while sending the file. Please try again.",
            parent=parent,
        )


# ── Pipe logic ─────────────────────────────────────────────────────────────────

def send_via_pipe(file_path: str) -> None:
    """Write *file_path* to the SyncDose named pipe.

    Opens ``\\\\.\\pipe\\FileSend`` in write-only mode, encodes the path as
    UTF-8, writes it in a single call, and closes the handle.

    On failure a :class:`QApplication` is created (if one does not already
    exist) and the appropriate error dialog is shown modally before the
    process exits.

    Args:
        file_path: Absolute path of the file the user wants to transfer.
    """
    try:
        handle = win32file.CreateFile(
            PIPE_NAME,
            win32file.GENERIC_WRITE,
            0,
            None,
            win32file.OPEN_EXISTING,
            0,
            None,
        )
        win32file.WriteFile(handle, file_path.encode("utf-8"))
        win32file.CloseHandle(handle)

    except pywintypes.error as exc:
        app: QApplication = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
        if exc.winerror == _WINERROR_PIPE_NOT_FOUND:
            PhoneNotDetectedDialog().exec()
        else:
            TransferErrorDialog().exec()

    except Exception:
        app: QApplication = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
        TransferErrorDialog().exec()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        send_via_pipe(sys.argv[1])

"""
File-handler error dialogs for the SyncDose file-send shell extension.

These dialogs run inside a **standalone PyInstaller executable** that has no
access to the main app's Qt virtual resource filesystem.  QSS is therefore
loaded from the bundled filesystem via :func:`utils.styles.load_stylesheet_disk`.
"""
import sys
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget, QApplication

from app.theme_manager import theme_manager
from resources.colors import HandlerDialogColors, LightHandlerDialogColors, Palette
from resources.spacing import Spacing
from utils.styles import load_stylesheet_disk, themed

# Path to the shared QSS template, relative to the resources/ directory.
_QSS_REL_PATH: Final[str] = "styles/handlers/handler-dialog.qss"


class _BaseHandlerDialog(QDialog):
    """Dark-themed notification dialog for file-handler error states.

    Renders a centered accent circle icon, a bold heading, an explanatory
    body message, a primary "Try Again" button, and a neutral "Dismiss"
    button. Subclasses supply the accent color, icon character, title,
    and message.

    Clicking **Try Again** resolves the dialog as :attr:`QDialog.Accepted`.
    Clicking **Dismiss** resolves it as :attr:`QDialog.Rejected`.

    Args:
        accent: Six-digit hex color string (e.g. ``"#22D3EE"``) applied to
            the icon circle and primary button gradient start.
        icon_char: Single character rendered inside the icon circle.
        title: Short, bold heading displayed below the circle.
        message: One-to-two sentence body text that guides the user.
        parent: Optional Qt parent widget.
    """

    _DIALOG_WIDTH: Final[int] = 340
    _ICON_SIZE: Final[int] = 52  # diameter of the icon circle in pixels
    _BUTTON_HEIGHT: Final[int] = 40

    def __init__(
            self,
            accent: str,
            icon_char: str,
            title: str,
            message: str,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._accent: str = accent
        self._icon_char: str = icon_char
        self._title: str = title
        self._message: str = message

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("HandlerDialog")
        self.setWindowTitle("SyncDose")
        self.setFixedWidth(self._DIALOG_WIDTH)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
        )
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        self._icon_circle: QLabel = self._create_icon_circle()
        self._title_label: QLabel = self._create_title_label()
        self._message_label: QLabel = self._create_message_label()
        self._try_again_button: QPushButton = self._create_try_again_button()
        self._dismiss_button: QPushButton = self._create_dismiss_button()

    def _setup_layout(self) -> None:
        root: QVBoxLayout = QVBoxLayout(self)
        # top: 32px  |  sides: 24px  |  bottom: 24px  (mirrors mockup padding)
        root.setContentsMargins(
            Spacing.XXL,
            Spacing.XXL + Spacing.SM,
            Spacing.XXL,
            Spacing.XXL,
        )
        root.setSpacing(Spacing.NONE)

        root.addWidget(self._icon_circle, 0, Qt.AlignmentFlag.AlignCenter)
        root.addSpacing(Spacing.XL)  # 20px — icon → title
        root.addWidget(self._title_label)
        root.addSpacing(Spacing.SM)  # 8px  — title → message
        root.addWidget(self._message_label)
        root.addSpacing(Spacing.XXL)  # 24px — message → buttons
        root.addWidget(self._try_again_button)
        root.addSpacing(Spacing.SM)  # 8px gap between buttons
        root.addWidget(self._dismiss_button)

    def _create_icon_circle(self) -> QLabel:
        circle = QLabel(self._icon_char)
        circle.setObjectName("IconCircle")
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        circle.setFixedSize(self._ICON_SIZE, self._ICON_SIZE)
        return circle

    def _create_title_label(self) -> QLabel:
        label = QLabel(self._title)
        label.setObjectName("TitleLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _create_message_label(self) -> QLabel:
        label = QLabel(self._message)
        label.setObjectName("MessageLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _create_try_again_button(self) -> QPushButton:
        btn = QPushButton("Try Again")
        btn.setObjectName("TryAgainButton")
        btn.setFixedHeight(self._BUTTON_HEIGHT)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _create_dismiss_button(self) -> QPushButton:
        btn = QPushButton("Dismiss")
        btn.setObjectName("DismissButton")
        btn.setFixedHeight(self._BUTTON_HEIGHT)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    # ── Styling ────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_rgba(hex_color: str, alpha: int) -> str:
        # Qt QSS parses 8-digit hex as #AARRGGBB, not #RRGGBBAA, so rgba() is
        # the only unambiguous way to express a hex color with an alpha channel.
        h = hex_color.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"

    def _apply_style(self) -> None:
        qss: str = load_stylesheet_disk(
            _QSS_REL_PATH,
            themed([HandlerDialogColors], [LightHandlerDialogColors], theme_manager.is_dark),
        )
        qss = (
            qss
            .replace("{{ACCENT}}", self._accent)
            .replace("{{ICON_BG}}", self._to_rgba(self._accent, 26))  # ~10 %
            .replace("{{ICON_BORDER}}", self._to_rgba(self._accent, 77))  # ~30 %
        )
        self.setStyleSheet(qss)

    # ── Signals ────────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._try_again_button.clicked.connect(self.accept)  # → Accepted
        self._dismiss_button.clicked.connect(self.reject)  # → Rejected
        theme_manager.theme_changed.connect(self._apply_style)


# ── Concrete dialogs ───────────────────────────────────────────────────────────
class PhoneNotDetectedDialog(_BaseHandlerDialog):
    """Shown when the SyncDose named pipe is not open.

    This means either the main app is not running or the phone is not yet
    connected.  Guides the user to open SyncDose, connect their phone, and
    click Try Again.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize with the phone-not-detected copy and cyan accent."""
        super().__init__(
            accent=Palette.CYAN_400,
            icon_char="⊗",
            title="Phone Not Detected",
            message=(
                "Make sure SyncDose is open and your phone is connected,"
                "then try again."
            ),
            parent=parent,
        )


class TransferErrorDialog(_BaseHandlerDialog):
    """Shown when an unexpected error occurs while writing to the named pipe.

    Covers all failure modes other than a missing pipe (e.g. broken handle,
    access-denied, encoding errors).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize with the generic-error copy and cyan accent."""
        super().__init__(
            accent=Palette.CYAN_400,
            icon_char="!",
            title="An Error Occurred",
            message="Something went wrong while sending the file. Please try again.",
            parent=parent,
        )

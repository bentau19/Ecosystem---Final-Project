"""
File-handler error dialogs for the SyncDose file-send shell extension.

These dialogs run inside a **standalone PyInstaller executable** that has no
access to the main app's Qt virtual resource filesystem.  QSS is therefore
loaded from the bundled filesystem via :func:`utils.styles.load_stylesheet_disk`.
"""
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from resources.colors import HandlerDialogColors, Palette
from resources.spacing import Spacing
from utils.styles import load_stylesheet_disk

# Path to the shared QSS template, relative to the resources/ directory.
_QSS_REL_PATH: Final[str] = "styles/handlers/handler-dialog.qss"


class _BaseHandlerDialog(QDialog):
    """Dark-themed notification dialog base for file-handler error states.

    Renders an accent-colored icon strip, a bold heading, an explanatory body
    message, and a single dismiss button.  Sub-classes supply the accent color,
    icon character, title, and message — all structural and styling logic is
    shared here.

    Args:
        accent: Six-digit hex color string (e.g. ``"#FF9800"``) applied to
            the icon strip background tint and dismiss button.
        icon_char: Emoji or single character rendered inside the icon strip.
        title: Short, bold heading displayed below the strip.
        message: One-to-two sentence body text that guides the user.
        parent: Optional Qt parent widget.
    """

    _DIALOG_WIDTH:  Final[int] = 400   # slightly wider canvas
    _STRIP_HEIGHT:  Final[int] = 88    # emoji needs vertical breathing room
    _BUTTON_HEIGHT: Final[int] = 40    # more substantial CTA
    _BUTTON_WIDTH:  Final[int] = 144   # compact centered pill, not full-width

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
        """Configure window properties, then create widgets and layout."""
        self.setObjectName("HandlerDialog")
        self.setWindowTitle("SyncDose")
        self.setFixedWidth(self._DIALOG_WIDTH)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
        )

        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        """Instantiate all child widgets and store as instance attributes."""
        self._icon_strip: QLabel = self._create_icon_strip()
        self._title_label: QLabel = self._create_title_label()
        self._message_label: QLabel = self._create_message_label()
        self._dismiss_button: QPushButton = self._create_dismiss_button()

    def _setup_layout(self) -> None:
        """Arrange child widgets in a vertical layout."""
        root: QVBoxLayout = QVBoxLayout(self)
        # bottom foot: XXL+SM = 32px
        root.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.XXL + Spacing.SM)
        root.setSpacing(Spacing.NONE)

        root.addWidget(self._icon_strip)
        root.addSpacing(Spacing.XXL)           # was XL (20px) → 24px

        body: QVBoxLayout = QVBoxLayout()
        # side gutters: XXL+SM = 32px each side (was 24px)
        body.setContentsMargins(Spacing.XXL + Spacing.SM, Spacing.NONE, Spacing.XXL + Spacing.SM, Spacing.NONE)
        body.setSpacing(Spacing.NONE)
        body.addWidget(self._title_label)
        body.addSpacing(Spacing.MD)            # was SM (8px) → 12px
        body.addWidget(self._message_label)
        body.addSpacing(Spacing.XXL)           # was XL (20px) → 24px
        # AlignCenter respects the button's fixed width and centers it
        body.addWidget(self._dismiss_button, 0, Qt.AlignmentFlag.AlignCenter)

        root.addLayout(body)

    def _create_icon_strip(self) -> QLabel:
        """Return the accent-colored strip containing the icon character.

        Returns:
            A :class:`QLabel` fixed to :attr:`_STRIP_HEIGHT` pixels,
            centered horizontally.
        """
        strip = QLabel(self._icon_char)
        strip.setObjectName("IconStrip")
        strip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        strip.setFixedHeight(self._STRIP_HEIGHT)
        return strip

    def _create_title_label(self) -> QLabel:
        """Return the centered, word-wrapped heading label.

        Returns:
            A :class:`QLabel` with the dialog title text.
        """
        label = QLabel(self._title)
        label.setObjectName("TitleLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _create_message_label(self) -> QLabel:
        """Return the centered, word-wrapped body-text label.

        Returns:
            A :class:`QLabel` with the explanatory message text.
        """
        label = QLabel(self._message)
        label.setObjectName("MessageLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _create_dismiss_button(self) -> QPushButton:
        """Return the compact centered OK button.

        Returns:
            A :class:`QPushButton` with fixed dimensions, centered by the
            layout via :attr:`Qt.AlignmentFlag.AlignCenter`.
        """
        btn = QPushButton("OK")
        btn.setObjectName("DismissButton")
        btn.setFixedHeight(self._BUTTON_HEIGHT)
        btn.setFixedWidth(self._BUTTON_WIDTH)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    # ── Styling ────────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        """Load the QSS template from disk and inject accent-derived tokens.

        Static color tokens are resolved by :func:`~utils.styles.load_stylesheet_disk`
        via :class:`~resources.colors.HandlerDialogColors`.  Accent-derived
        placeholders — ``{{ACCENT}}``, ``{{STRIP_BG}}``, ``{{ACCENT_HOVER}}``,
        ``{{ACCENT_PRESSED}}`` — are replaced manually because they vary per
        dialog variant and cannot live in a static enum.
        """
        qss: str = load_stylesheet_disk(_QSS_REL_PATH, [HandlerDialogColors])

        # Inject accent-derived dynamic tokens
        qss = (
            qss
            .replace("{{ACCENT}}",         self._accent)
            .replace("{{STRIP_BG}}",        f"{self._accent}22")  # ~13 % opacity tint
            .replace("{{ACCENT_HOVER}}",    f"{self._accent}CC")  # ~80 % opacity
            .replace("{{ACCENT_PRESSED}}",  f"{self._accent}99")  # ~60 % opacity
        )

        self.setStyleSheet(qss)

    # ── Signals ────────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        """Wire widget signals to slots."""
        self._dismiss_button.clicked.connect(self.accept)


# ── Concrete dialogs ───────────────────────────────────────────────────────────

class PhoneNotDetectedDialog(_BaseHandlerDialog):
    """Shown when the SyncDose named pipe is not open.

    This means either the main app is not running or the phone is not yet
    connected.  Guides the user to open SyncDose, connect their phone, and retry.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize with the phone-not-detected copy and orange accent."""
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

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize with the generic-error copy and pink accent."""
        super().__init__(
            accent=Palette.PINK_500,
            icon_char="⚠️",
            title="An Error Occurred",
            message="Something went wrong while sending the file. Please try again.",
            parent=parent,
        )

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from app.theme_manager import theme_manager
from resources.colors import LightPalette, Palette
from resources.spacing import Spacing

# ── Layout constants ──────────────────────────────────────────────────────────
_DIALOG_WIDTH: int = 340
_ICON_SIZE: int = 54
_BUTTON_HEIGHT: int = 44

# Bluetooth glyph rendered inside the accent circle (the rune the Bluetooth logo derives from).
_ICON_CHAR: str = "ᛒ"


def _build_qss(is_dark: bool) -> str:
    """Return the dialog QSS with colors resolved for the active theme."""
    p = Palette if is_dark else LightPalette
    cyan = Palette.CYAN_400          # accent — invariant across themes
    cyan_pressed = "#0891b2"         # sky-600 — pressed state of the primary button

    return f"""
    QDialog#ConnectionApprovalDialog {{
        background-color: {p.DARK_900};
        color: {p.SLATE_100};
    }}
    QLabel#IconCircle {{
        background-color: rgba(34, 211, 238, 0.12);
        border: 1px solid rgba(34, 211, 238, 0.45);
        border-radius: {_ICON_SIZE // 2}px;
        color: {cyan};
        font-size: 26px;
    }}
    QLabel#TitleLabel {{
        color: {p.SLATE_100};
        font-size: 18px;
        font-weight: 600;
    }}
    QLabel#MessageLabel {{
        color: {p.SLATE_500};
        font-size: 14px;
    }}
    QPushButton#AllowButton {{
        background-color: {cyan};
        border: none;
        border-radius: 10px;
        color: {p.DARK_900};
        font-size: 15px;
        font-weight: 600;
    }}
    QPushButton#AllowButton:hover {{
        background-color: {cyan_pressed};
    }}
    QPushButton#RejectButton {{
        background-color: transparent;
        border: 1px solid {p.GRAY_700};
        border-radius: 10px;
        color: {p.SLATE_100};
        font-size: 15px;
    }}
    QPushButton#RejectButton:hover {{
        border-color: {p.SLATE_500};
    }}
    """


class ConnectionApprovalDialog(QDialog):
    """Accept/reject dialog shown when a new phone asks to connect over Bluetooth.

    Mirrors the SyncDose handler-dialog style (accent icon circle, bold title, body message,
    primary + neutral buttons). **Allow** resolves the dialog as :attr:`QDialog.Accepted`,
    **Reject** (or close) as :attr:`QDialog.Rejected`.

    Args:
        phone_name: The connecting phone's name, shown in the body text.
        parent: Optional Qt parent widget.
    """

    def __init__(self, phone_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phone_name = phone_name
        self._setup_ui()
        self._apply_style()
        theme_manager.theme_changed.connect(self._apply_style)

    def _setup_ui(self) -> None:
        self.setObjectName("ConnectionApprovalDialog")
        self.setWindowTitle("SyncDose")
        self.setFixedWidth(_DIALOG_WIDTH)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)

        icon = QLabel(_ICON_CHAR)
        icon.setObjectName("IconCircle")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(_ICON_SIZE, _ICON_SIZE)

        title = QLabel("Connection request")
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)

        message = QLabel(f'“{self._phone_name}” wants to connect over Bluetooth.')
        message.setObjectName("MessageLabel")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)

        allow_btn = QPushButton("Allow")
        allow_btn.setObjectName("AllowButton")
        allow_btn.setFixedHeight(_BUTTON_HEIGHT)
        allow_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        allow_btn.clicked.connect(self.accept)

        reject_btn = QPushButton("Reject")
        reject_btn.setObjectName("RejectButton")
        reject_btn.setFixedHeight(_BUTTON_HEIGHT)
        reject_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reject_btn.clicked.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XXL, Spacing.XXL + Spacing.SM, Spacing.XXL, Spacing.XXL)
        root.setSpacing(Spacing.NONE)
        root.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)
        root.addSpacing(Spacing.XL)
        root.addWidget(title)
        root.addSpacing(Spacing.SM)
        root.addWidget(message)
        root.addSpacing(Spacing.XXL)
        root.addWidget(allow_btn)
        root.addSpacing(Spacing.SM)
        root.addWidget(reject_btn)

    def _apply_style(self) -> None:
        self.setStyleSheet(_build_qss(theme_manager.is_dark))

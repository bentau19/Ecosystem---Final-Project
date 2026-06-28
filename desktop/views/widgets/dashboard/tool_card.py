from PySide6.QtCore import Signal, QPropertyAnimation, QEasingCurve, QPoint, QEvent
from PySide6.QtGui import QColor, QMouseEvent, QPixmap, Qt, QIcon, QEnterEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QFrame

from app.theme_manager import theme_manager
from resources.colors import ToolCardColors, LightToolCardColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from views.widgets.settings.toggle_switch import ToggleSwitch


class ToolCard(QFrame):
    """A dashboard card with an icon, title, description and an enable toggle.

    Hovering raises the card by 2px (animated). The card body emits ``clicked``
    only when constructed ``clickable`` (e.g. the "Send File" action card);
    feature cards are inert apart from their toggle switch. An optional ``hint``
    line is shown beneath the description (e.g. "Open Explorer to view").

    Signals:
        clicked: Emitted when a *clickable* card body is left-clicked.
        toggled: Emitted with the new checked state when the toggle is flipped
            by the user (not when changed programmatically via
            :meth:`set_checked_silent`).
    """

    clicked: Signal = Signal()
    toggled: Signal = Signal(bool)

    def __init__(
            self,
            icon: QIcon,
            icon_background: QColor,
            title: str,
            content_widget: QWidget,
            checked: bool = True,
            checkable: bool = True,
            clickable: bool = True,
            hint: str = "",
            icon_width: int = 30,
            icon_height: int = 30,
            parent: QWidget | None = None
    ) -> None:
        """Initialize the dashboard card widget.

        Args:
            icon: The icon to display.
            icon_background: The background color of the icon.
            title: The title of the dashboard card.
            content_widget: The widget to display as the description content.
            checked: Initial toggle state. Defaults to ``True``.
            checkable: Whether to show an enable/disable toggle. Defaults to ``True``.
            clickable: Whether the card body emits ``clicked``. Defaults to ``True``.
            hint: Optional hint text shown under the description. Defaults to ``""``.
            icon_width: The width of the icon. Defaults to ``30``.
            icon_height: The height of the icon. Defaults to ``30``.
            parent: Optional parent widget. Defaults to ``None``.
        """
        super().__init__(parent)

        self._icon: QIcon = icon
        self._icon_background: QColor = icon_background
        self._title: str = title
        self._content_widget: QWidget = content_widget
        self._checked: bool = checked
        self._checkable: bool = checkable
        self._clickable: bool = clickable
        self._hint: str = hint
        self._icon_width: int = icon_width
        self._icon_height: int = icon_height

        self._icon_label: QLabel
        self._title_label: QLabel
        self._toggle: ToggleSwitch | None = None

        self.anim: QPropertyAnimation

        self._setup_ui()
        self._setup_style()
        self._connect_signals()

    def _setup_ui(self) -> None:
        # Set object name, configure animation, set cursor, then build widgets and layout.
        self.setObjectName("card")

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(100)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._create_widgets()

        # Only clickable (action) cards get the pointing-hand affordance.
        if self._clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._create_layout()

    def _create_widgets(self) -> None:
        # Create icon label, title label, and (optionally) the enable toggle.
        self._icon_label = self._create_icon_label()
        self._title_label = self._create_title_label()
        if self._checkable:
            self._toggle = ToggleSwitch(checked=self._checked)

    def _create_layout(self) -> None:
        # Build the vertical card layout: icon → (title + toggle) → description → hint.
        layout: QVBoxLayout = QVBoxLayout(self)

        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.XS)

        layout.addWidget(self._icon_label)
        layout.addSpacing(Spacing.SM)

        # Title row: title on the left, enable toggle on the right.
        title_row: QHBoxLayout = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(self._title_label)
        title_row.addStretch()
        if self._toggle is not None:
            title_row.addWidget(self._toggle)
        layout.addLayout(title_row)

        layout.addSpacing(Spacing.SM)
        layout.addWidget(self._content_widget)

        if self._hint:
            layout.addWidget(self._create_hint_label())

        layout.addStretch()

    def _setup_style(self) -> None:
        # Load themed QSS and append the per-card icon background color rule.
        qss: str = load_stylesheet(
            DashboardStyles.TOOL_CARD,
            themed([ToolCardColors], [LightToolCardColors], theme_manager.is_dark),
        )
        qss += f"#icon {{ background: {self._icon_background.name().upper()}; }}"
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        # Re-apply stylesheet on theme change; forward toggle flips as `toggled`.
        theme_manager.theme_changed.connect(self._setup_style)
        if self._toggle is not None:
            self._toggle.toggled.connect(self.toggled)

    def set_checked_silent(self, checked: bool) -> None:
        """Reflect an externally-driven enabled state without emitting ``toggled``.

        Used when the state changes from elsewhere (the viewmodel, or a push from
        the phone) so the write-back into the viewmodel is not re-triggered.

        Args:
            checked: New checked (on) state.
        """
        self._checked = checked
        if self._toggle is not None:
            self._toggle.set_checked_silent(checked)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Emit ``clicked`` on a left-click — only for clickable cards.

        Args:
            event: The mouse release event delivered by Qt.
        """
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _create_title_label(self) -> QLabel:
        # Create a left-aligned title label.
        title_label: QLabel = QLabel(self._title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title_label.setObjectName("titleLabel")
        return title_label

    def _create_hint_label(self) -> QLabel:
        # Create a left-aligned, word-wrapped hint/status label.
        hint: QLabel = QLabel(self._hint)
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignLeft)
        return hint

    def _create_icon_label(self) -> QLabel:
        # Create a fixed-size icon label scaled to card icon dimensions.
        icon_label: QLabel = QLabel()
        icon_pixmap: QPixmap = self._icon.pixmap(self._icon_width, self._icon_height)
        icon_label.setPixmap(icon_pixmap)
        icon_label.setObjectName("icon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(self._icon_width + 16, self._icon_height + 16)
        return icon_label

    def enterEvent(self, event: QEnterEvent) -> None:
        """Animate the card up by 2px on hover.

        Args:
            event: The enter event delivered by Qt.
        """
        super().enterEvent(event)
        self.anim.setEndValue(self.pos() - QPoint(0, 2))
        self.anim.start()

    def leaveEvent(self, event: QEvent) -> None:
        """Animate the card back down by 2px on hover-out.

        Args:
            event: The leave event delivered by Qt.
        """
        super().leaveEvent(event)
        self.anim.setEndValue(self.pos() + QPoint(0, 2))
        self.anim.start()

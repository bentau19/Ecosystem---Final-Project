from PySide6.QtCore import Signal, QPropertyAnimation, QEasingCurve, QPoint, QEvent
from PySide6.QtGui import QColor, QMouseEvent, QPixmap, Qt, QIcon, QEnterEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QFrame

from app.theme_manager import theme_manager
from resources.colors import ToolCardColors, LightToolCardColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed


class ToolCard(QFrame):
    """A widget that displays a dashboard card with an icon, title, and content.

    Hovering raises the card by 2px (animated); leaving lowers it back.

    Signals:
        clicked: Emitted when the card is left-clicked.
    """

    clicked: Signal = Signal()

    def __init__(
            self,
            icon: QIcon,
            icon_background: QColor,
            title: str,
            content_widget: QWidget,
            icon_width: int = 30,
            icon_height: int = 30,
            parent: QWidget | None = None
    ) -> None:
        """Initialize the dashboard card widget.

        Args:
            icon: The icon to display.
            icon_background: The background color of the icon.
            title: The title of the dashboard card.
            content_widget: The widget to display as the content.
            icon_width: The width of the icon. Defaults to ``30``.
            icon_height: The height of the icon. Defaults to ``30``.
            parent: Optional parent widget. Defaults to ``None``.
        """
        super().__init__(parent)

        self._icon: QIcon = icon
        self._icon_background: QColor = icon_background
        self._title: str = title
        self._content_widget: QWidget = content_widget
        self._icon_width: int = icon_width
        self._icon_height: int = icon_height

        self._icon_label: QLabel
        self._title_label: QLabel

        self.anim: QPropertyAnimation

        self._setup_ui()
        self._setup_style()
        self._connect_signals()

    def _setup_ui(self) -> None:
        # Set object name, configure animation, set cursor, then build widgets and layout.
        self.setObjectName("card")

        self.anim: QPropertyAnimation = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(100)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._create_widgets()

        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._create_layout()

    def _create_widgets(self) -> None:
        # Create icon label and title label children.
        self._icon_label = self._create_icon_label()
        self._title_label = self._create_title_label()

    def _create_layout(self) -> None:
        # Build the vertical card layout: icon → title → content → stretch.
        layout: QVBoxLayout = QVBoxLayout(self)

        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.XS)

        # set widgets
        layout.addWidget(self._icon_label)
        layout.addSpacing(Spacing.SM)
        layout.addWidget(self._title_label)
        layout.addSpacing(Spacing.SM)
        layout.addWidget(self._content_widget)
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
        # Wire theme_changed to re-apply the stylesheet.
        theme_manager.theme_changed.connect(self._setup_style)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release events.

        Args:
            event: The mouse release event delivered by Qt.

        Emits:
            clicked: When the released button is the left mouse button.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _create_title_label(self) -> QLabel:
        # Create a left-aligned title label.
        title_label: QLabel = QLabel(self._title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title_label.setObjectName("titleLabel")

        return title_label

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
        """Handle the enter event for the widget.

        Animates the widget to move up by 2 pixels.

        Args:
            event: The enter event delivered by Qt.
        """
        super().enterEvent(event)

        self.anim.setEndValue(self.pos() - QPoint(0, 2))
        self.anim.start()

    def leaveEvent(self, event: QEvent) -> None:
        """Handle the leave event for the widget.

        Animates the widget to move back down by 2 pixels.

        Args:
            event: The leave event delivered by Qt.
        """
        super().leaveEvent(event)
        self.anim.setEndValue(self.pos() + QPoint(0, 2))
        self.anim.start()

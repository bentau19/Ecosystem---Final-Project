from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QPixmap, QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame

from resources.colors import NavigationColors
from resources.paths import NavigationStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet


class NavigationItem(QFrame):
    """
    A navigation item widget with an icon and text for navigation menus.

    Supports active/inactive states, hover effects, cursor changes,
    and emits a signal when clicked.
    """

    clicked: Signal = Signal()

    def __init__(self, icon: QPixmap, item_title: str, is_active: bool = False, parent: QWidget | None = None) -> None:
        """
        Initialize the navigation item.

        Args:
            icon (QPixmap): The icon to display.
            item_title (str): Text displayed next to the icon.
            is_active (bool, optional): Whether the item starts in the active state. Defaults to False.
            parent (QWidget | None, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)

        self._is_active: bool = is_active
        self._icon: QPixmap = icon
        self._item_title: str = item_title

        self._icon_label: QLabel
        self._text_label: QLabel

        self._setup_ui()
        self._setup_style()

    def _setup_ui(self) -> None:
        """Initialize widget, layout, and styles."""
        self.setProperty("isActive", self._is_active)
        self._set_cursor_and_height()

        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        """Create icon and text labels."""
        self._icon_label = self._create_icon()
        self._text_label = self._create_text_label()

    def _create_layout(self) -> None:
        """Create and configure the horizontal layout."""
        layout: QHBoxLayout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(
            Spacing.XS,
            Spacing.XS,
            Spacing.XS,
            Spacing.XS,
        )
        layout.setSpacing(Spacing.XS)

        layout.addSpacing(Spacing.SM)

        layout.addWidget(self._icon_label)
        layout.addWidget(self._text_label)

    def _set_cursor_and_height(self) -> None:
        """Set cursor and fixed height for the widget."""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(45)

    def _create_icon(self) -> QLabel:
        """
        Create the icon label.

        Returns:
            QLabel configured for the icon.
        """
        icon_label: QLabel = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        icon_label.setFixedWidth(40)
        icon_label.setPixmap(
            self._icon.scaled(26, 26, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        icon_label.setObjectName("iconLabel")
        return icon_label

    def _create_text_label(self) -> QLabel:
        """
        Create the text label.

        Returns:
            QLabel configured for the text.
        """
        text_label: QLabel = QLabel(self._item_title)
        text_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        text_label.setObjectName("textLabel")
        text_label.setProperty("isActive", self._is_active)
        return text_label

    def _setup_style(self) -> None:
        """Load and apply the stylesheet with color placeholders replaced."""
        qss: str = load_stylesheet(NavigationStyles.ITEM, [NavigationColors])
        self.setStyleSheet(qss)

    def _change_hover_status(self, value: bool) -> None:
        """Update hover property and refresh styling."""
        self._text_label.setProperty("hovered", value)
        self.style().unpolish(self._text_label)
        self.style().polish(self._text_label)
        self.update()

    def enterEvent(self, event: QEnterEvent) -> None:
        """Handle mouse enter events."""
        super().enterEvent(event)
        self._change_hover_status(True)

    def leaveEvent(self, event: QEvent) -> None:
        """Handle mouse leave events."""
        super().leaveEvent(event)
        self._change_hover_status(False)

    @property
    def is_active(self) -> bool:
        """Return whether this navigation item is active."""
        return self._is_active

    @is_active.setter
    def is_active(self, value: bool) -> None:
        """Set active state and update UI."""

        self._is_active = value
        self.setProperty("isActive", value)
        self._text_label.setProperty("isActive", value)

        for widget in (self, self._text_label):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Emit clicked signal on left mouse release."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

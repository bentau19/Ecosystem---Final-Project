from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QColor, QMouseEvent, Qt, QIcon, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QFrame

from app.theme_manager import theme_manager
from resources.colors import InfoCardColors, LightInfoCardColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed


class InfoCard(QFrame):
    """
    A widget that displays a dashboard card with an icon, title, and content.
    """

    clicked = Signal()

    def __init__(self, icon: QIcon, icon_background: QColor,
                 title: str, content_widget: QWidget, icon_width: int = 30, icon_height: int = 30,
                 parent: QWidget | None = None) -> None:
        """
        Initialize the dashboard card widget.

        Args:
            icon (QIcon): The icon to display.
            icon_background (QColor): The background color of the icon.
            title (str): The title of the dashboard card.
            content_widget (QWidget): The widget to display as the content.
            icon_width (int, optional): The width of the icon. Defaults to 30.
            icon_height (int, optional): The height of the icon. Defaults to 30.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)

        self._icon: QIcon = icon
        self._icon_background: QColor = icon_background
        self._title: str = title
        self._content_widget: QWidget = content_widget
        self._icon_width: int = icon_width
        self._icon_height: int = icon_height

        self._anim: QPropertyAnimation

        self._setup_ui()
        self._setup_style()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """
        Set up the UI for the dashboard card.
        """
        self.setObjectName("card")

        self._anim: QPropertyAnimation = QPropertyAnimation(self, b'pos')
        self._anim.setDuration(100)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._create_widgets()

        self._create_layout()

    def _create_widgets(self) -> None:
        """
        Create the child widgets for the dashboard card.
        """
        self._icon_label: QLabel = self._create_icon_label()
        self._title_label: QLabel = self._create_title_label()

    def _create_layout(self) -> None:
        """
        Create and configure the layout for the dashboard card.
        """
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
        """Apply the stylesheet to the dashboard card."""
        qss: str = load_stylesheet(
            DashboardStyles.INFO_CARD,
            themed([InfoCardColors], [LightInfoCardColors], theme_manager.is_dark),
        )
        qss += f'#icon {{ background: {self._icon_background.name().upper()}; }}'
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        """Wire theme changes to re-apply the stylesheet."""
        theme_manager.theme_changed.connect(self._setup_style)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse release events.

        Emits a clicked signal when the left mouse button is released.

        Args:
            event (QMouseEvent): The mouse event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _create_title_label(self) -> QLabel:
        """
        Create a title label for the dashboard card.

        Returns:
            QLabel: The title label.
        """
        title_label: QLabel = QLabel(self._title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title_label.setObjectName('titleLabel')

        return title_label

    def _create_icon_label(self) -> QLabel:
        """
        Create an icon label for the dashboard card.

        Returns:
            QLabel: The icon label.
        """
        icon_label: QLabel = QLabel()
        icon_pixmap: QPixmap = self._icon.pixmap(self._icon_width, self._icon_height)
        icon_label.setPixmap(icon_pixmap)
        icon_label.setObjectName('icon')
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(self._icon_width + 16, self._icon_height + 16)
        return icon_label

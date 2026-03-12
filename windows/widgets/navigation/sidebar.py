from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout

from resources.resources import Resources
from utils.styles import load_stylesheet
from widgets.divider import Divider
from widgets.indicators.pill_wraper import PillWrapper
from widgets.navigation.logo_widget import LogoWidget
from widgets.navigation.nav_container import NavigationContainer


class Sidebar(QWidget):
    """
    Sidebar widget containing the main application navigation.

    Includes:
        - Application logo
        - Navigation container with navigation items
        - Pill wrapper indicators
        - Dividers for visual separation
    """

    # Sidebar fixed width
    _SIDEBAR_WIDTH: Final[int] = 230

    # Layout margins and spacing
    _MARGIN_LEFT: Final[int] = 0
    _MARGIN_RIGHT: Final[int] = 0
    _MARGIN_TOP: Final[int] = 0
    _MARGIN_BOTTOM: Final[int] = 20
    _SPACING: Final[int] = 0

    def __init__(self, parent: QWidget | None = None):
        """
        Initialize the Sidebar widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize child widgets, layout, and apply styles."""
        self._create_widgets()
        self._create_layout()

        self.setFixedWidth(self._SIDEBAR_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._apply_styles()

    def _create_widgets(self) -> None:
        """Instantiate all child widgets used in the sidebar."""
        self._logo_widget = LogoWidget()
        self._nav_container = NavigationContainer()
        self._pill_wrapper = PillWrapper()

    def _create_layout(self) -> None:
        """Set up the vertical layout and add widgets with spacing and dividers."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self._MARGIN_LEFT,
            self._MARGIN_TOP,
            self._MARGIN_RIGHT,
            self._MARGIN_BOTTOM
        )
        layout.setSpacing(self._SPACING)

        layout.addWidget(self._logo_widget)
        layout.addWidget(Divider())
        layout.addWidget(self._nav_container)
        layout.addStretch()
        layout.addWidget(Divider())
        layout.addWidget(self._pill_wrapper)

    def _apply_styles(self) -> None:
        """Load and apply the QSS stylesheet for the sidebar."""
        qss: str = load_stylesheet(Resources.SIDEBAR_QSS_PATH)
        self.setStyleSheet(qss)
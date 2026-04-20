from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame

from resources.colors import SidebarColors
from resources.paths import NavigationStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet
from views.widgets.divider import Divider
from views.widgets.indicators.pill_wraper import PillWrapper
from views.widgets.logo_widget import LogoWidget
from views.widgets.navigation.container import NavigationContainer


class Sidebar(QFrame):
    """
    Sidebar widget containing the main application navigation.

    Includes:
        - Application logo
        - Navigation container with navigation items
        - Pill wrapper indicators
        - Dividers for visual separation
    """

    def __init__(
            self, sidebar_width: int = 230, logo_widget_height: int = 120, parent: QWidget | None = None
    ) -> None:
        """
        Initialize the Sidebar widget.

        Args:
            sidebar_width (int, optional): The width of the sidebar. Defaults to 230.
            logo_widget_height (int, optional): The height of the logo widget. Defaults to 120.
            parent (Optional[QWidget], optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)

        self._logo_widget_height: int = logo_widget_height
        self._sidebar_width: int = sidebar_width

        self._logo_widget: LogoWidget
        self._nav_container: NavigationContainer
        self._pill_wrapper: PillWrapper

        self._setup_ui()
        self._setup_style()

    def _setup_ui(self) -> None:
        """Initialize child widgets, layout, and apply styles."""
        self._create_widgets()
        self._create_layout()
        self.setFixedWidth(self._sidebar_width)

    def _create_widgets(self) -> None:
        """Instantiate all child widgets used in the sidebar."""
        self._logo_widget = self._create_logo_widget()
        self._nav_container = NavigationContainer()
        self._pill_wrapper = PillWrapper()

    def _create_layout(self) -> None:
        """Set up the vertical layout and add widgets with spacing and dividers."""
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.SM)
        layout.setSpacing(Spacing.NONE)

        layout.addWidget(self._logo_widget)
        layout.addWidget(Divider())
        layout.addWidget(self._nav_container)
        layout.addStretch()
        layout.addWidget(Divider())
        layout.addWidget(self._pill_wrapper)

    def _setup_style(self) -> None:
        """Load and apply the QSS stylesheet for the sidebar."""
        qss: str = load_stylesheet(NavigationStyles.SIDEBAR, [SidebarColors])
        self.setStyleSheet(qss)

    def _create_logo_widget(self) -> LogoWidget:
        """
        Create the logo widget.

        Returns:
            LogoWidget: The logo widget.
        """
        widget: LogoWidget = LogoWidget()
        widget.setFixedHeight(self._logo_widget_height)
        return widget
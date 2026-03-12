from typing import Final

from PySide6.QtCore import Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from resources.resources import Resources
from resources.strings import Strings
from utils.styles import load_stylesheet
from widgets.navigation.navigation_item import NavigationItem


class NavigationContainer(QWidget):
    """
    A QWidget that contains the application's navigation items.

    The container displays a section label and multiple navigation
    items, managing which item is currently active.
    """

    # Layout configuration
    _MARGIN_LEFT: Final[int] = 12
    _MARGIN_RIGHT: Final[int] = 12
    _MARGIN_TOP: Final[int] = 5
    _MARGIN_BOTTOM: Final[int] = 0
    _SPACING: Final[int] = 2

    _LABEL_OBJECT_NAME: Final[str] = "navigationSectionLabel"

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the navigation container."""
        super().__init__(parent)
        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        """Initialize widgets, layout, and styles."""
        self._create_widgets()
        self._setup_layout()
        self._apply_styles()

    def _create_widgets(self) -> None:
        """Create all child widgets used in the navigation container."""
        # self._nav_label = SectionLabel(Strings.NAVIGATION_GENERAL_SECTION)
        self._navigation_label = self._create_navigation_label()

        self._first_navigation_item = NavigationItem(
            QPixmap(Resources.DASHBOARD_ICON_PATH),
            Strings.NAVIGATION_DASHBOARD_LABEL,
            is_active=True,
        )

        self._second_navigation_item = NavigationItem(
            QPixmap(Resources.SETTINGS_ICON_PATH),
            Strings.NAVIGATION_SETTINGS_LABEL,

        )

        # Track the currently active navigation item
        self._active_navigation_item: NavigationItem = self._first_navigation_item

    def _setup_layout(self) -> None:
        """Create and configure the vertical layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self._MARGIN_LEFT,
            self._MARGIN_TOP,
            self._MARGIN_RIGHT,
            self._MARGIN_BOTTOM,
        )
        layout.setSpacing(self._SPACING)

        layout.addWidget(self._navigation_label)
        layout.addWidget(self._first_navigation_item)
        layout.addWidget(self._second_navigation_item)
        layout.addStretch()

    def _apply_styles(self) -> None:
        """Load and apply the stylesheet for the navigation container."""
        qss: str = load_stylesheet(Resources.NAVIGATION_CONTAINER_QSS_PATH)
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        """Connect navigation item signals."""
        self._first_navigation_item.clicked.connect(
            lambda: self._change_active_status(self._first_navigation_item)
        )

        self._second_navigation_item.clicked.connect(
            lambda: self._change_active_status(self._second_navigation_item)
        )

    @Slot()
    def _change_active_status(self, navigation_item: NavigationItem) -> None:
        """
        Update the active navigation item.

        If the selected item is already active, no change occurs.
        Otherwise, the previously active item is deactivated and the
        new item becomes active.

        Args:
            navigation_item: The navigation item that was clicked.
        """
        if navigation_item == self._active_navigation_item:
            return

        navigation_item.is_active = True
        self._active_navigation_item.is_active = False
        self._active_navigation_item = navigation_item

    def _create_navigation_label(self) -> QLabel:
        """
        Create the navigation label widget.

        This function creates a QLabel widget with the text set to
        Strings.NAVIGATION_GENERAL_SECTION. The label object name is
        set to self._LABEL_OBJECT_NAME.

        Returns:
            QLabel: The navigation label widget.
        """
        label: QLabel = QLabel(Strings.NAVIGATION_GENERAL_SECTION)
        label.setObjectName(self._LABEL_OBJECT_NAME)
        return label

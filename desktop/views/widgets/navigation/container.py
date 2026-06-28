from PySide6.QtCore import Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from app.navigation_manager import navigation_manager
from app.theme_manager import theme_manager
from domain.enums.screen import Screen
from resources.colors import Colors, LightColors
from resources.paths import Icons, NavigationStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from views.widgets.navigation.item import NavigationItem

# Maps each nav-item list position to the screen it navigates to.
_NAV_SCREENS: list[Screen] = [Screen.DASHBOARD, Screen.SETTINGS]


class NavigationContainer(QWidget):
    """A QWidget that contains the application's navigation items.

    The container displays a section label and multiple navigation
    items, managing which item is currently active and triggering
    screen navigation via :data:`~app.navigation_manager.navigation_manager`.
    """

    def __init__(self, active_index: int = 0, parent: QWidget | None = None) -> None:
        """Initialize the navigation container.

        Args:
            active_index: Index of the nav item that should start in the
                active (highlighted) state.  ``0`` = Dashboard, ``1`` = Settings.
                Defaults to ``0``.
            parent: Optional parent widget. Defaults to ``None``.
        """
        super().__init__(parent)

        self._active_index: int = active_index
        self._navigation_label: QLabel
        self._navigation_items: list[NavigationItem]
        self._active_navigation_item: NavigationItem

        self._setup_ui()
        self._setup_style()
        self._setup_signals()

    def _setup_ui(self) -> None:
        # Create widgets and build the vertical layout.
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        # Instantiate the section label and both navigation items.
        # The item at self._active_index starts in the active state.
        self._navigation_label = self._create_navigation_label()

        first_navigation_item: NavigationItem = NavigationItem(
            QPixmap(Icons.DASHBOARD),
            self.tr("Dashboard"),
            is_active=(self._active_index == 0),
        )

        second_navigation_item: NavigationItem = NavigationItem(
            QPixmap(Icons.SETTINGS),
            self.tr("Settings"),
            is_active=(self._active_index == 1),
        )
        self._navigation_items = [first_navigation_item, second_navigation_item]

        self._active_navigation_item = self._navigation_items[self._active_index]

    def _setup_layout(self) -> None:
        # Build the vertical layout: section label → nav items → trailing stretch.
        layout: QVBoxLayout = QVBoxLayout(self)

        layout.setContentsMargins(Spacing.LG, Spacing.XS, Spacing.LG, Spacing.NONE)
        layout.setSpacing(Spacing.SM)

        layout.addWidget(self._navigation_label)
        for item in self._navigation_items:
            layout.addWidget(item)
        layout.addStretch()

    def _setup_style(self) -> None:
        # Load and apply the themed container stylesheet.
        qss: str = load_stylesheet(
            NavigationStyles.CONTAINER,
            themed([Colors], [LightColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _setup_signals(self) -> None:
        # Wire each item's clicked signal and theme_changed to their slots.
        for item in self._navigation_items:
            item.clicked.connect(lambda i=item: self._change_active_status(i))
        theme_manager.theme_changed.connect(self._setup_style)
        # Keep every live NavigationContainer in sync with the actual active
        # screen — including containers on screens that are currently hidden.
        navigation_manager.navigate.connect(self._on_navigate)

    @Slot(NavigationItem)
    def _change_active_status(self, navigation_item: NavigationItem) -> None:
        # Deactivate the previous item and activate the clicked one; no-op if already active.
        if navigation_item == self._active_navigation_item:
            return

        navigation_item.is_active = True
        self._active_navigation_item.is_active = False
        self._active_navigation_item = navigation_item

        # Navigate to the corresponding screen.
        idx: int = self._navigation_items.index(navigation_item)
        if idx < len(_NAV_SCREENS):
            navigation_manager.go_to_screen(_NAV_SCREENS[idx])

    @Slot(int)
    def _on_navigate(self, screen_index: int) -> None:
        """Sync the highlighted nav item to whichever screen just became active.

        Called on every navigation event so all live NavigationContainers
        (including the one on the screen that is no longer visible) stay
        consistent with the actual active screen.

        Args:
            screen_index: The :class:`~domain.enums.screen.Screen` integer value
                emitted by :attr:`~app.navigation_manager.NavigationManager.navigate`.
        """
        try:
            screen = Screen(screen_index)
        except ValueError:
            return  # Unknown screen index — ignore.
        if screen not in _NAV_SCREENS:
            return  # No nav item for this screen (e.g. LOGIN).
        target = self._navigation_items[_NAV_SCREENS.index(screen)]
        if target == self._active_navigation_item:
            return  # Already correct — nothing to repaint.
        self._active_navigation_item.is_active = False
        target.is_active = True
        self._active_navigation_item = target

    def _create_navigation_label(self) -> QLabel:
        # Return the 'General' section heading label.
        label: QLabel = QLabel(self.tr("General"))
        label.setObjectName("navigationSectionLabel")
        return label

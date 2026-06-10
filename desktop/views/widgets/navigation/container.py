from PySide6.QtCore import Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from app.theme_manager import theme_manager
from resources.colors import Colors, LightColors
from resources.paths import Icons, NavigationStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from views.widgets.navigation.item import NavigationItem


class NavigationContainer(QWidget):
    """A QWidget that contains the application's navigation items.

    The container displays a section label and multiple navigation
    items, managing which item is currently active.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the navigation container.

        Args:
            parent: Optional parent widget. Defaults to ``None``.
        """
        super().__init__(parent)

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
        self._navigation_label = self._create_navigation_label()

        first_navigation_item: NavigationItem = NavigationItem(
            QPixmap(Icons.DASHBOARD),
            self.tr("Dashboard"),
            is_active=True,
        )

        second_navigation_item: NavigationItem = NavigationItem(
            QPixmap(Icons.SETTINGS),
            self.tr("Settings"),
        )
        self._navigation_items = [first_navigation_item, second_navigation_item]

        self._active_navigation_item = first_navigation_item

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

    @Slot(NavigationItem)
    def _change_active_status(self, navigation_item: NavigationItem) -> None:
        # Deactivate the previous item and activate the clicked one; no-op if already active.
        if navigation_item == self._active_navigation_item:
            return

        navigation_item.is_active = True
        self._active_navigation_item.is_active = False
        self._active_navigation_item = navigation_item

    def _create_navigation_label(self) -> QLabel:
        # Return the 'General' section heading label.
        label: QLabel = QLabel(self.tr("General"))
        label.setObjectName("navigationSectionLabel")
        return label

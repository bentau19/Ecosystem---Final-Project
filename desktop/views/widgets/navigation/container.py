from PySide6.QtCore import Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from resources.colors import NavigationColors
from resources.paths import Icons, NavigationStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet
from views.widgets.navigation.item import NavigationItem


class NavigationContainer(QWidget):
    """
    A QWidget that contains the application's navigation items.

    The container displays a section label and multiple navigation
    items, managing which item is currently active.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the navigation container.

        Args:
            parent (Optional[QWidget]): Parent widget, defaults to None.
        """
        super().__init__(parent)

        self._navigation_label: QLabel
        self._navigation_items: list[NavigationItem]
        self._active_navigation_item: NavigationItem

        self._setup_ui()
        self._setup_style()
        self._setup_signals()

    def _setup_ui(self) -> None:
        """Initialize widgets, layout, and styles."""
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        """Create all child widgets used in the navigation container."""
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
        """Create and configure the vertical layout."""
        layout: QVBoxLayout = QVBoxLayout(self)

        layout.setContentsMargins(Spacing.LG, Spacing.XS, Spacing.LG, Spacing.NONE)
        layout.setSpacing(Spacing.SM)

        layout.addWidget(self._navigation_label)
        for item in self._navigation_items:
            layout.addWidget(item)
        layout.addStretch()

    def _setup_style(self) -> None:
        """Load and apply the stylesheet for the navigation container."""
        qss: str = load_stylesheet(NavigationStyles.CONTAINER, [NavigationColors])
        self.setStyleSheet(qss)

    def _setup_signals(self) -> None:
        """Connect navigation item signals."""
        for item in self._navigation_items:
            item.clicked.connect(lambda i=item: self._change_active_status(i))

    @Slot(NavigationItem)
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
        """Create the section heading label ('General').

        Returns:
            A ``QLabel`` with the ``navigationSectionLabel`` object name set.
        """
        label: QLabel = QLabel(self.tr("General"))
        label.setObjectName("navigationSectionLabel")
        return label

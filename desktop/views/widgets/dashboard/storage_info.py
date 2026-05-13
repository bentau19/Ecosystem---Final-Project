from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QLabel, QFrame, QWidget

from app.theme_manager import theme_manager
from resources.colors import Colors, LightColors, StorageBarColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from views.widgets.bar import Bar


class StorageInfo(QFrame):
    """Compact card widget showing storage usage with a gradient progress bar.

    Displays used/total storage in gigabytes, a filled bar proportional to
    usage, and a percentage sub-label. Styled via QSS.
    """

    def __init__(
            self,
            total_space: int = 256,
            used_space: int = 126,
            parent: QWidget | None = None,
    ) -> None:
        """Initialize the StorageInfo widget.

        Args:
            total_space (int): The total available storage space.
            used_space (int): The amount of storage space currently used.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)

        self._available_space: int = total_space
        self._used_space: int = used_space


        self._percentage: int = int((self._used_space / self._available_space) * 100)

        self._value_label: QLabel
        self._bar: Bar
        self._sub_label: QLabel

        self._setup_ui()
        self._setup_style()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Create and configure the vertical layout for the storage card."""
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        """Create all child widgets for the storage card."""
        self._value_label = self._create_value_label()

        self._bar = Bar(self._percentage, QColor(StorageBarColors.GRADIENT_START),
                        QColor(StorageBarColors.GRADIENT_END))
        self._sub_label = self._create_sub_label()

    def _create_layout(self) -> None:
        """Create and configure the vertical layout for the storage card.

        Sets up a QVBoxLayout with specific margins and spacing, then adds
        all child widgets in the correct order with appropriate spacing.
        """
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        layout.addWidget(self._value_label)
        layout.addSpacing(Spacing.SM)
        layout.addWidget(self._bar)
        layout.addSpacing(Spacing.SM)
        layout.addWidget(self._sub_label)
        layout.addStretch()

    def _setup_style(self) -> None:
        """Apply card styling to the storage card."""
        qss: str = load_stylesheet(
            DashboardStyles.STORAGE_INFO,
            themed([Colors], [LightColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        """Wire theme changes to re-apply the stylesheet."""
        theme_manager.theme_changed.connect(self._setup_style)

    def _create_value_label(self) -> QLabel:
        """Create the storage usage value label.

        Returns:
            QLabel: A label displaying "128 / 256 GB" with text color,
                   larger font, bold weight, and transparent background
        """
        label: QLabel = QLabel(f"{self._used_space} / {self._available_space} GB")
        label.setObjectName("storageValue")
        return label

    def _create_sub_label(self) -> QLabel:
        """Create the usage percentage sub-label.

        Returns:
            QLabel: A label displaying "50% used" with muted color and small font
        """
        label: QLabel = QLabel(f"{self._percentage}% used")
        label.setObjectName("storageSubLabel")
        return label

from typing import Optional

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QLabel, QFrame, QWidget

from resources.colors import DashboardColors, StorageBarColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet
from views.widgets.bar import Bar


class StorageInfo(QFrame):
    def __init__(
            self,
            total_space: int = 256,
            used_space: int = 126,
            parent: Optional[QWidget] = None,
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

        self._value_label: QLabel
        self._bar: Bar
        self._sub_label: QLabel

        self._setup_ui()
        self._setup_style()

    def _setup_ui(self) -> None:
        """Create and configure the vertical layout for the storage card."""
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        """Create all child widgets for the storage card."""
        self._value_label = self._create_value_label()

        self._bar = Bar(50, QColor(StorageBarColors.GRADIENT_START), QColor(StorageBarColors.GRADIENT_END))
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
        """Apply card styling to the storage card.

        Sets the background, border, and border-radius to create a card appearance
        using the application's color scheme.
        """
        qss: str = load_stylesheet(DashboardStyles.STORAGE_INFO, [DashboardColors])
        self.setStyleSheet(qss)

    def _create_value_label(self) -> QLabel:
        """Create the storage usage value label.

        Returns:
            QLabel: A label displaying "128 / 256 GB" with text color,
                   larger font, bold weight, and transparent background
        """
        label: QLabel = QLabel(f"{self._used_space} / {self._available_space} GB")
        label.setObjectName("storageValue")
        return label


    @staticmethod
    def _create_sub_label() -> QLabel:
        """Create the usage percentage sub-label.

        Returns:
            QLabel: A label displaying "50% used" with muted color and small font
        """
        label: QLabel = QLabel("50% used")
        label.setObjectName("storageSubLabel")
        return label

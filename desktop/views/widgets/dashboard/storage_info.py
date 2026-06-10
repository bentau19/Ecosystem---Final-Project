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
            total_space: The total available storage space, in gigabytes.
            used_space: The amount of storage space currently used, in gigabytes.
            parent: Optional parent widget. Defaults to ``None``.
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
        # Create widgets and build the vertical layout.
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        # Create the value label, gradient bar, and percentage sub-label.
        self._value_label = self._create_value_label()

        self._bar = Bar(self._percentage, QColor(StorageBarColors.GRADIENT_START),
                        QColor(StorageBarColors.GRADIENT_END))
        self._sub_label = self._create_sub_label()

    def _create_layout(self) -> None:
        # Build the vertical card layout: value → bar → sub-label → stretch.
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        layout.addWidget(self._value_label)
        layout.addSpacing(Spacing.SM)
        layout.addWidget(self._bar)
        layout.addSpacing(Spacing.SM)
        layout.addWidget(self._sub_label)
        layout.addStretch()

    def _setup_style(self) -> None:
        # Load and apply the themed QSS.
        qss: str = load_stylesheet(
            DashboardStyles.STORAGE_INFO,
            themed([Colors], [LightColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        # Wire theme_changed to re-apply the stylesheet.
        theme_manager.theme_changed.connect(self._setup_style)

    def _create_value_label(self) -> QLabel:
        # Create the 'used / total GB' display label.
        label: QLabel = QLabel(f"{self._used_space} / {self._available_space} GB")
        label.setObjectName("storageValue")
        return label

    def _create_sub_label(self) -> QLabel:
        # Create the 'N% used' muted sub-label.
        label: QLabel = QLabel(f"{self._percentage}% used")
        label.setObjectName("storageSubLabel")
        return label

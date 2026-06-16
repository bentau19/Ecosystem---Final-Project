from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QVBoxLayout, QFrame, QWidget

from app.theme_manager import theme_manager
from resources.colors import Colors, LightColors, BatteryBarColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from views.widgets.bar import Bar


class BatteryInfo(QFrame):
    """Compact card widget showing battery percentage with a gradient progress bar.

    Displays the percentage value, a filled bar, and a charging status label.
    Styled via QSS.
    """

    def __init__(
            self, battery_percentage: int, is_charging: bool, parent: QWidget | None = None
    ) -> None:
        """Initialize the BatteryInfo widget.

        Creates all child widgets, sets up the layout, applies styling,
        and sets the object name for CSS targeting.

        Args:
            battery_percentage: Battery percentage (0-100).
            is_charging: Whether the battery is currently charging.
            parent: Optional parent widget. Defaults to ``None``.
        """
        super().__init__(parent)

        self._battery_percentage: int = battery_percentage
        self._is_charging: bool = is_charging

        self._setup_ui()
        self.setup_style()
        self._connect_signals()

    def _setup_ui(self) -> None:
        # Create widgets and build the vertical layout.
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        # Create value label, gradient bar, and charging status label.
        self._battery_value_label: QLabel = self._create_battery_value_label()
        self._battery_bar: Bar = self._create_battery_bar()
        self._charging_label: QLabel = self._create_charging_label()

    def _create_layout(self) -> None:
        # Build the vertical card layout: percentage → bar → charging label → stretch.
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)

        layout.addWidget(self._battery_value_label)
        layout.addSpacing(Spacing.XS)

        layout.addWidget(self._battery_bar)

        layout.addSpacing(Spacing.XS)

        layout.addWidget(self._charging_label)

        layout.addStretch()

    def setup_style(self) -> None:
        """Load and apply QSS styling to the battery card."""
        qss = load_stylesheet(
            DashboardStyles.BATTERY_INFO,
            themed([Colors], [LightColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        # Wire theme_changed to re-apply the stylesheet.
        theme_manager.theme_changed.connect(self.setup_style)

    def _create_battery_value_label(self) -> QLabel:
        # Create the 'N%' percentage display label.
        percentage_str = f"{self._battery_percentage}%"
        val = QLabel(percentage_str)
        val.setObjectName("batteryValue")
        return val

    def _create_battery_bar(self) -> Bar:
        # Create the gradient fill bar scaled to current battery percentage.
        bar = Bar(self._battery_percentage, QColor(BatteryBarColors.GRADIENT_START), QColor(
            BatteryBarColors.GRADIENT_END))
        bar.setObjectName("batteryBar")
        return bar

    @staticmethod
    def _create_charging_label() -> QLabel:
        # Create the charging status label (static text for now).
        charging = QLabel("⚡ Charging… ~35 min to full")
        charging.setObjectName("batteryCharging")
        return charging

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QVBoxLayout, QFrame, QWidget
from typing import Optional

from resources.colors import DashboardColors, BatteryBarColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet
from views.widgets.bar import Bar


class BatteryInfo(QFrame):
    """A compact card widget that displays battery information with a visual indicator.

    This widget shows battery status including percentage, a progress bar,
    charging.svg status, and an icon. It's styled using QSS and displays
    battery information in a compact card format.

    Args:
        battery_percentage (int): Battery percentage (0-100).
        is_charging (bool): Whether the battery is currently charging.
        parent (Optional[QWidget]): Parent widget, defaults to None.
    """

    def __init__(
            self, battery_percentage: int, is_charging: bool, parent: Optional[QWidget] = None
    ) -> None:
        """Initialize the BatteryInfo widget.

        Creates all child widgets, sets up the layout, applies styling,
        and sets the object name for CSS targeting.

        Args:
            battery_percentage (int): Battery percentage (0-100).
            is_charging (bool): Whether the battery is currently charging.
            parent (Optional[QWidget]): Parent widget, defaults to None.
        """
        super().__init__(parent)

        self._battery_percentage = battery_percentage
        self._is_charging = is_charging

        self._setup_ui()
        self.setup_style()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        """Create all child widgets for the battery card."""
        self._battery_value_label: QLabel = self._create_battery_value_label()
        self._battery_bar: Bar = self._create_battery_bar()
        self._charging_label: QLabel = self._create_charging_label()

    def _create_layout(self) -> None:
        """Create and configure the vertical layout for the battery card."""
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
        qss = load_stylesheet(DashboardStyles.BATTERY_INFO, [DashboardColors])
        self.setStyleSheet(qss)

    def _create_battery_value_label(self) -> QLabel:
        """Create the battery percentage value label.

        Returns:
            QLabel: A label displaying battery percentage.
        """
        percentage_str = f"{self._battery_percentage}%"
        val = QLabel(percentage_str)
        val.setObjectName("batteryValue")
        return val

    def _create_battery_bar(self) -> Bar:
        """Create the battery level progress bar.

        Returns:
            BatteryBar: A battery bar widget showing battery charge.
        """
        bar = Bar(self._battery_percentage,QColor( BatteryBarColors.GRADIENT_START),QColor (
            BatteryBarColors.GRADIENT_END))
        bar.setObjectName("batteryBar")
        return bar

    @staticmethod
    def _create_charging_label() -> QLabel:
        """Create the charging.svg status label.

        Returns:
            QLabel: A label displaying charging.svg status with lightning bolt icon and time estimate.
        """
        charging = QLabel("⚡ Charging… ~35 min to full")
        charging.setObjectName("batteryCharging")
        return charging

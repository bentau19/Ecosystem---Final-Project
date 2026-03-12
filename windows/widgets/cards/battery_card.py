from typing import Final

from PySide6.QtCore import Qt, QFile, QTextStream
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout

from resources.colors import Colors
from resources.resources import Resources
from resources.strings import Strings
from utils.styles import load_stylesheet
from widgets.battery_bar import BatteryBar


class BatteryCard(QWidget):
    """A card widget that displays battery information with a visual indicator.
    
    This widget shows battery status including percentage, a progress bar,
    charging.svg status, and an icon. It's styled using QSS and displays
    battery information in a compact card format.
    
    Args:
        parent (Optional[QWidget]): Parent widget, defaults to None
    """

    # Private constants
    _BATTERY_QSS_NAME: Final[str] = "batteryCard"  # Object name used in QSS for the logo icon
    _BATTERY_TITLE_QSS_NAME: Final[str] = "batteryTitle"  # Object name used in QSS for the app name label
    _BATTERY_VALUE_QSS_NAME: Final[str] = "batteryValue"  # Object name used in QSS for the app name label
    _LOGO_SIZE: Final[int] = 70  # Diameter of the circular logo

    _MARGIN_LEFT: Final[int] = 10
    _MARGIN_RIGHT: Final[int] = 20
    _MARGIN_TOP: Final[int] = 20
    _MARGIN_BOTTOM: Final[int] = 20
    _SPACING: Final[int] = 10  # Layout spacing between logo and label

    def __init__(self, battery_percentage: int, is_charging: bool, parent=None):
        """Initialize the BatteryCard widget.
        
        Creates all child widgets, sets up the layout, applies styling,
        and sets the object name for CSS targeting.
        
        Args:
            parent (Optional[QWidget]): Parent widget, defaults to None
        """
        super().__init__(parent)

        self._battery_percentage = battery_percentage
        self._is_charging = is_charging
        self._setup_ui()

    def _setup_ui(self):
        self._create_widgets()
        self._create_layout()

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName(self._BATTERY_QSS_NAME)
        self._load_style()

    def _create_widgets(self) -> None:
        """Create all child widgets for the battery card.
        
        Instantiates the title label, battery value label, battery bar,
        charging.svg label, and icon label components.
        """
        self._title_label: QLabel = self._create_title_label()
        self._battery_value_label: QLabel = self._create_battery_value_label()
        self._battery_bar: BatteryBar = self._create_battery_bar()
        self._charging_label: QLabel = self._create_charging_label()
        self._icon_label: QLabel = self._create_icon_label()

    def _create_title_label(self) -> QLabel:
        """Create the title label for the battery card.
        
        Returns:
            QLabel: A label displaying title
        """
        label = QLabel(Strings.BATTERY_CARD_TITLE)
        label.setObjectName(self._BATTERY_TITLE_QSS_NAME)
        return label

    def _create_battery_value_label(self) -> QLabel:
        """Create the battery percentage value label.
        
        Returns:
            QLabel: A label displaying battery percentage
        """
        percentage_str = f"%{self._battery_percentage}"
        val = QLabel(percentage_str)
        val.setObjectName(self._BATTERY_VALUE_QSS_NAME)
        return val

    @staticmethod
    def _create_battery_bar() -> BatteryBar:
        """Create the battery level progress bar.
        
        Returns:
            BatteryBar: A battery bar widget showing battery charge
        """
        bar = BatteryBar(78)
        bar.setObjectName("batteryBar")
        return bar

    @staticmethod
    def _create_charging_label() -> QLabel:
        """Create the charging.svg status label.
        
        Returns:
            QLabel: A label displaying charging.svg status with lightning bolt icon and time estimate
        """

        charging = QLabel("⚡  Charging… ~35 min to full")
        charging.setObjectName("batteryCharging")
        return charging

    @staticmethod
    def _create_icon_label() -> QLabel:
        """Create the battery icon label.
        
        Returns:
            QLabel: A label with lightning bolt icon, fixed size 30x30, centered alignment
        """

        icon_label = QLabel("⚡")
        icon_label.setObjectName("batteryIcon")
        icon_label.setFixedSize(30, 30)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return icon_label

    def _load_style(self):
        """Load and apply QSS styling to the battery card."""
        qss = load_stylesheet(Resources.BATTERY_CARD_QSS_PATH)
        self.setStyleSheet(qss)

    def _create_layout(self):
        """Create and configure the vertical layout for the battery card.
        
        Sets up a QVBoxLayout with specific margins and spacing, then adds
        all child widgets in the correct order with appropriate spacing.
        """
        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)

        layout.setSpacing(4)

        layout.addWidget(self._icon_label)

        layout.addSpacing(6)

        layout.addWidget(self._title_label)

        layout.addWidget(self._battery_value_label)
        layout.addSpacing(4)

        layout.addWidget(self._battery_bar)

        layout.addSpacing(4)

        layout.addWidget(self._charging_label)

        layout.addStretch()

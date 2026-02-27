import qtawesome as qta
from PySide6.QtGui import QColor, QIcon, Qt
from PySide6.QtWidgets import QVBoxLayout, QLabel, QFrame

from view.widgets.progress_bar import BatteryLevelWidget
from windows.view.widgets.phone_card_item import PhoneCardItemWidget


class PhoneCardWidget(QFrame):
    def __init__(self, device_name: str, device_type: str, battery_percentage: int, charging: bool) -> None:
        super().__init__()

        self.device_name: str = device_name
        self.device_type: str = device_type
        self.battery_percentage: int = battery_percentage
        self.charging: bool = charging
        self.battery_icons: dict[int, QIcon] = {
            0: qta.icon("fa6s.battery-empty", color="orange"),
            1: qta.icon("fa6s.battery-quarter", color="orange"),
            2: qta.icon("fa6s.battery-half", color="orange"),
            3: qta.icon("fa6s.battery-three-quarters", color="orange"),
            4: qta.icon("fa6s.battery-full", color="orange"),
        }

        self.device_type_icons: dict[str, QIcon] = {
            "android": qta.icon("ph.android-logo", color="purple"),
        }

        self.init_ui()

        self._load_style()

    def init_ui(self) -> None:
        main_layout: QVBoxLayout = QVBoxLayout()
        main_layout.setObjectName("card")

        self.setLayout(main_layout)
        self._create_device_name_item()
        self._create_device_type_item()
        self._create_battery_info_item()

    def _create_device_name_item(self) -> None:
        desc: str = "Device Name"
        device_name_label: QLabel = QLabel(self.device_name)
        device_name_label.setObjectName("device_name_label")

        img_icon: QIcon = qta.icon("msc.device-mobile", color="#578CFD")
        background_color: QColor = QColor()
        background_color.setRgb(219, 234, 254)

        device_name_item: PhoneCardItemWidget = PhoneCardItemWidget(desc, device_name_label, img_icon, background_color)
        self.layout().addWidget(device_name_item)

    def _create_device_type_item(self) -> None:
        desc: str = "Device Type"
        device_type_label: QLabel = QLabel(self.device_type)
        device_type_label.setObjectName("device_type_label")
        img_icon: QIcon = qta.icon("msc.device-mobile", color="#9810FA")
        background_color: QColor = QColor()
        background_color.setRgb(243, 232, 255)

        device_name_item: PhoneCardItemWidget = PhoneCardItemWidget(desc, device_type_label, img_icon, background_color)
        self.layout().addWidget(device_name_item)

    def _get_battery_icon(self) -> QIcon:
        if self.charging:
            return qta.icon("ri.battery-charge-line", color="orange")

        battery_quarter_percentage: int = self.battery_percentage // 25
        return self.battery_icons[battery_quarter_percentage]

    def _create_battery_info_item(self) -> None:
        battery_icon: QIcon = self._get_battery_icon()

        icon_background_color: QColor = QColor()
        icon_background_color.setRgb(254, 249, 194)

        battery_progress: BatteryLevelWidget = BatteryLevelWidget(self.battery_percentage, self.charging)
        battery_info_item: PhoneCardItemWidget = PhoneCardItemWidget("Battery Level", battery_progress, battery_icon,
                                                                     icon_background_color)

        self.layout().addWidget(battery_info_item)

    def _load_style(self) -> None:
        """Load and apply the external QSS stylesheet from ``../qss/phone_card.qss``.

        :raises FileNotFoundError: If the QSS file does not exist at the expected path.
        """
        with open("../qss/phone_card.qss", "r") as f:
            self.setStyleSheet(f.read())

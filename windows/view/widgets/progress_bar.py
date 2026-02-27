from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QProgressBar, QLabel


class BatteryLevelWidget(QWidget):
    def __init__(self, battery_percentage: int, charging: bool):
        super().__init__()
        self.battery_percentage = battery_percentage
        self.charging = charging

        self._load_style()
        self.init_ui()

    def init_ui(self) -> None:
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        second_layout = QHBoxLayout()
        progress_bar: QProgressBar = QProgressBar(minimum=0, maximum=100, orientation=Qt.Orientation.Horizontal,
                                                  value=self.battery_percentage)
        progress_bar.setTextVisible(False)
        second_layout.addWidget(progress_bar)
        percentage_label = QLabel(str(f"{self.battery_percentage}%"))
        second_layout.addWidget(percentage_label)
        main_layout.addLayout(second_layout)

        if self.charging:
            charging_status_label = QLabel("charging...")
            main_layout.addWidget(charging_status_label)

        self.setLayout(main_layout)

    def _load_style(self) -> None:
        """Load and apply the external QSS stylesheet from ``../qss/phone_card_item.qss``.

        :raises FileNotFoundError: If the QSS file does not exist at the expected path.
        """
        with open("../qss/battery_level.qss", "r") as f:
            self.setStyleSheet(f.read())

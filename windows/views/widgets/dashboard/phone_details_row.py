from typing import List, Optional

from PySide6.QtCore import Slot
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget, )

from dto.device_info import DeviceBatteryInfoDTO, DeviceGeneralInfoDTO, DeviceStorageInfoDTO, DeviceBaseInfoDTO
from layouts.flow_layout import FlowLayout
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet
from viewmodels.device_info import DeviceInfoViewModel
from views.widgets.dashboard.battery_info import BatteryInfo
from views.widgets.dashboard.info_card import InfoCard
from views.widgets.dashboard.storage_info import StorageInfo


class PhoneDetailsRow(QWidget):
    def __init__(
            self,
            card_width: int = 200,
            card_height: int = 200,
            parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the DeviceStatusRow widget.

        Args:
            card_width: Width of the cards.
            card_height: Height of the cards.
            parent (Optional[QWidget], optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)

        self._card_width: int = card_width
        self._card_height: int = card_height

        self._device_info_view_model: DeviceInfoViewModel = DeviceInfoViewModel()

        self._main_layout: FlowLayout

        self._cards: List[InfoCard] = []

        self._setup_ui()
        self._setup_style()
        self._setup_signals()

        self._device_info_view_model.load_device_infos()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        """Create all child widgets for the device status row."""
        pass

    def _create_layout(self) -> None:
        """Create and configure the horizontal layout."""
        self._main_layout = FlowLayout(min_width=self._card_width, parent=self)
        self._main_layout.setSpacing(Spacing.LG)

    @staticmethod
    def _create_title_description_widget(
            first_description: str, second_description: str
    ) -> QWidget:
        """Create a widget with a first description and a second description.

        Args:
            first_description: The first description.
            second_description: The second description.

        Returns:
            QWidget: The created widget.
        """
        widget: QWidget = QWidget()
        layout: QVBoxLayout = QVBoxLayout(widget)
        layout.setContentsMargins(
            Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE
        )

        primary_description_label: QLabel = QLabel(first_description)
        primary_description_label.setObjectName("primaryDescription")

        secondary_description_label: QLabel = QLabel(second_description)
        secondary_description_label.setObjectName("secondaryDescription")

        layout.addWidget(primary_description_label)
        layout.addWidget(secondary_description_label)

        return widget

    def _create_general_device_info(self, info: DeviceGeneralInfoDTO) -> InfoCard:
        """Create the device name.

        Args:
            info: The device info detail.

        Returns:
            InfoCard: The created device name.
        """
        content: QWidget = self._create_title_description_widget(
            info.title, info.description
        )
        card: InfoCard = InfoCard(
            QIcon(info.icon_path), QColor(info.icon_background_color), info.title, content
        )
        card.setMinimumWidth(self._card_width)
        card.setFixedHeight(self._card_height)
        return card

    def _create_battery(self, battery: DeviceBatteryInfoDTO) -> InfoCard:
        """Create the battery.

        Args:
            battery: The battery detail.

        Returns:
            InfoCard: The created battery.
        """
        card: InfoCard = InfoCard(
            QIcon(battery.icon_path),
            QColor(battery.icon_background_color),
            battery.title,
            BatteryInfo(battery.battery_percentage, battery.is_charging),
        )

        card.setMinimumWidth(self._card_width)
        card.setFixedHeight(self._card_height)
        return card

    def _create_storage(self, storage: DeviceStorageInfoDTO) -> InfoCard:
        """Create the storage.

        Args:
            storage: The storage detail.

        Returns:
            InfoCard: The created storage.
        """
        card: InfoCard = InfoCard(
            QIcon(storage.icon_path),
            QColor(storage.icon_background_color),
            storage.title,
            StorageInfo(storage.total_storage, storage.used_storage),
        )
        card.setMinimumWidth(self._card_width)
        card.setFixedHeight(self._card_height)
        return card

    def _setup_style(self) -> None:
        """Apply the stylesheet to the widget."""
        qss: str = load_stylesheet(DashboardStyles.DEVICE_STATUS_ROW)
        self.setStyleSheet(qss)

    def _setup_signals(self):
        # TODO: setup signals on changed device info,added deleted if needed
        self._device_info_view_model.device_infos_loaded.connect(self._on_device_infos_loaded)

    @Slot(list)
    def _on_device_infos_loaded(self, device_infos: List[DeviceBaseInfoDTO]) -> None:
        """Handle the signal when device infos are loaded.

        Args:
            device_infos (List[DeviceBaseInfoDTO]): The list of device base info DTOs.
        """
        for device_info in device_infos:
            if isinstance(device_info, DeviceBatteryInfoDTO):
                self._main_layout.addWidget(self._create_battery(device_info))
            if isinstance(device_info, DeviceStorageInfoDTO):
                self._main_layout.addWidget(self._create_storage(device_info))
            if isinstance(device_info, DeviceGeneralInfoDTO):
                self._main_layout.addWidget(self._create_general_device_info(device_info))

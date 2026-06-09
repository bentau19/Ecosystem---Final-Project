"""
Phone details row widget.

Renders a flow-layout row of device-info cards (name, OS, battery, storage)
populated from :class:`~viewmodels.device.DeviceViewModel`.  Cards are rebuilt
on every ``device_infos_updated`` signal so that reconnects always show fresh data.
"""
from PySide6.QtCore import Slot
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from domain.dto.device_info import (
    DeviceInfoDTO,
    DeviceNameDTO,
    DeviceOSDTO,
    DeviceBatteryDTO,
    DeviceStorageDTO,
)
from domain.enums.device_type import DeviceType
from views.layouts.flow_layout import FlowLayout
from app.app_state import app_state
from app.theme_manager import theme_manager
from resources.colors import Colors, InfoCardColors, LightColors
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from viewmodels.device import DeviceViewModel
from views.widgets.dashboard.battery_info import BatteryInfo
from views.widgets.dashboard.info_card import InfoCard
from views.widgets.dashboard.storage_info import StorageInfo


class PhoneDetailsRow(QWidget):
    """Scrollable row of device-info cards on the dashboard.

    On construction, it loads all device-info entities via the
    ``DeviceInfoViewModel`` and renders one ``InfoCard`` per entity.
    """

    _DEVICE_TYPE_COLORS: dict[DeviceType, str] = {
        DeviceType.NAME:    InfoCardColors.ICON_BG,
        DeviceType.OS:      InfoCardColors.ICON_BG,
        DeviceType.STORAGE: InfoCardColors.ICON_BG,
        DeviceType.BATTERY: InfoCardColors.ICON_BG,
    }

    def __init__(
            self,
            card_width: int = 200,
            card_height: int = 200,
            parent: QWidget | None = None,
    ) -> None:
        """Initialize the PhoneDetailsRow widget.

        Args:
            card_width:  Minimum width applied to every card.
            card_height: Fixed height applied to every card.
            parent:      Optional parent widget.
        """
        super().__init__(parent)

        self._card_width: int = card_width
        self._card_height: int = card_height

        self._device_viewmodel: DeviceViewModel = app_state.device_viewmodel

        self._main_layout: FlowLayout

        self._setup_ui()
        self._setup_style()
        self._setup_signals()


    def _setup_ui(self) -> None:
        # Create widgets and configure the flow layout.
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        # No static child widgets; cards are created dynamically in _set_device_infos.
        pass

    def _create_layout(self) -> None:
        # Create and configure the FlowLayout.
        self._main_layout = FlowLayout(min_width=self._card_width, parent=self)
        self._main_layout.setSpacing(Spacing.LG)

    @staticmethod
    def _create_description_widget(first_description: str) -> QWidget:
        # Create a single primary-line label widget inside a minimal container.
        widget: QWidget = QWidget()
        layout: QVBoxLayout = QVBoxLayout(widget)
        layout.setContentsMargins(
            Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE
        )

        primary_description_label: QLabel = QLabel(first_description)
        primary_description_label.setObjectName("primaryDescription")

        layout.addWidget(primary_description_label)

        return widget

    def _create_general_info_card(self, dto: DeviceInfoDTO) -> InfoCard:
        # Create a text-value InfoCard for DeviceNameDTO or DeviceOSDTO instances.
        card: InfoCard
        descr = ""
        color: str
        if isinstance(dto, DeviceNameDTO):
            descr = dto.name
            color = self._DEVICE_TYPE_COLORS[DeviceType.NAME]
        elif isinstance(dto, DeviceOSDTO):
            descr = dto.os
            color = self._DEVICE_TYPE_COLORS[DeviceType.OS]
        else:
            raise ValueError(f"Unknown device info type: {type(dto)}")

        content: QWidget = self._create_description_widget(descr)
        card: InfoCard = InfoCard(
            QIcon(dto.icon_path),
            QColor(color),
            dto.title,
            content,
        )
        card.setMinimumWidth(self._card_width)
        card.setFixedHeight(self._card_height)
        return card

    def _create_battery(self, battery: DeviceBatteryDTO) -> InfoCard:
        # Create the battery status InfoCard with a BatteryInfo content widget.
        card: InfoCard = InfoCard(
            QIcon(battery.icon_path),
            QColor(self._DEVICE_TYPE_COLORS[DeviceType.BATTERY]),
            battery.title,
            BatteryInfo(battery.level, battery.is_charging),
        )
        card.setMinimumWidth(self._card_width)
        card.setFixedHeight(self._card_height)
        return card

    def _create_storage(self, storage: DeviceStorageDTO) -> InfoCard:
        # Create the storage usage InfoCard with a StorageInfo content widget.
        card: InfoCard = InfoCard(
            QIcon(storage.icon_path),
            QColor(self._DEVICE_TYPE_COLORS[DeviceType.STORAGE]),
            storage.title,
            StorageInfo(storage.total, storage.used),
        )
        card.setMinimumWidth(self._card_width)
        card.setFixedHeight(self._card_height)
        return card

    def _setup_style(self) -> None:
        # Load and apply the themed QSS.
        qss: str = load_stylesheet(
            DashboardStyles.DEVICE_STATUS_ROW,
            themed([Colors], [LightColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _setup_signals(self) -> None:
        # Wire device_infos_updated and theme_changed to their slots.
        self._device_viewmodel.device_infos_updated.connect(self._set_device_infos)
        theme_manager.theme_changed.connect(self._setup_style)

    @Slot(list)
    def _set_device_infos(self, device_infos: list[DeviceInfoDTO]) -> None:
        # Clear existing cards before repopulating to avoid duplicates across
        # logout/login cycles (showEvent re-triggers load_device_info each time).
        while self._main_layout.count():
            item = self._main_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        # Create an InfoCard for each DTO and add it to the flow layout.
        for dto in device_infos:
            if isinstance(dto, DeviceBatteryDTO):
                self._main_layout.addWidget(self._create_battery(dto))
            elif isinstance(dto, DeviceStorageDTO):
                self._main_layout.addWidget(self._create_storage(dto))
            elif isinstance(dto, DeviceNameDTO):
                self._main_layout.addWidget(self._create_general_info_card(dto))
            elif isinstance(dto, DeviceOSDTO):
                self._main_layout.addWidget(self._create_general_info_card(dto))


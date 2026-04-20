from typing import List, Type

from PySide6.QtCore import Slot
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from dto.device_info import (
    DeviceInfoDTO,
    DeviceNameDTO,
    DeviceOSDTO,
    DeviceBatteryDTO,
    DeviceStorageDTO,
)
from enums.device_type import DeviceType
from layouts.flow_layout import FlowLayout
from resources.colors import Palette
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.viewmodel_manager import viewmodel_manager
from utils.styles import load_stylesheet
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
        DeviceType.NAME: Palette.CYAN_800,  # identity → mid-cyan tint
        DeviceType.OS: Palette.CYAN_800,  # system   → mid-cyan tint
        DeviceType.STORAGE: Palette.CYAN_800,  # storage  → mid-cyan tint
        DeviceType.BATTERY: Palette.CYAN_800,  # energy   → mid-cyan tint
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

        self._device_viewmodel: DeviceViewModel = viewmodel_manager.device_viewmodel

        self._main_layout: FlowLayout
        self._cards: List[InfoCard] = []

        self._setup_ui()
        self._setup_style()
        self._setup_signals()

        self._device_viewmodel.load_device_info()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        """Create all child widgets for the device status row."""
        pass

    def _create_layout(self) -> None:
        """Create and configure the flow layout."""
        self._main_layout = FlowLayout(min_width=self._card_width, parent=self)
        self._main_layout.setSpacing(Spacing.LG)

    @staticmethod
    def _create_description_widget(first_description: str) -> QWidget:
        """Create a single-line label widget.

        Args:
            first_description: Primary line of text to display.

        Returns:
            QWidget containing the label.
        """
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
        """Create a generic text-value card (name, OS, or IP).

        Args:
            dto: The DTO supplying title, icon, color, and text value.

        Returns:
            A configured ``InfoCard`` widget.
        """
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
        """Create the battery status card.

        Args:
            battery: The battery DTO.

        Returns:
            A configured ``InfoCard`` widget.
        """
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
        """Create the storage usage card.

        Args:
            storage: The storage DTO.

        Returns:
            A configured ``InfoCard`` widget.
        """
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
        """Apply the stylesheet to the widget."""
        qss: str = load_stylesheet(DashboardStyles.DEVICE_STATUS_ROW)
        self.setStyleSheet(qss)

    def _setup_signals(self) -> None:
        """Connect ViewModel signals to view slots."""
        self._device_viewmodel.device_infos_updated.connect(self._set_device_infos)

    @Slot(list)
    def _set_device_infos(self, device_infos: List[DeviceInfoDTO]) -> None:
        """Render an ``InfoCard`` for every loaded device-info DTO.

        Args:
            device_infos: List of ``DeviceInfoDTO`` subclass instances emitted
                by the ViewModel on initial load.
        """
        for dto in device_infos:
            if isinstance(dto, DeviceBatteryDTO):
                self._main_layout.addWidget(self._create_battery(dto))
            elif isinstance(dto, DeviceStorageDTO):
                self._main_layout.addWidget(self._create_storage(dto))
            elif isinstance(dto, DeviceNameDTO):
                self._main_layout.addWidget(self._create_general_info_card(dto))
            elif isinstance(dto, DeviceOSDTO):
                self._main_layout.addWidget(self._create_general_info_card(dto))

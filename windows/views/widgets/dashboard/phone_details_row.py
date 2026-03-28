from typing import List, Optional

from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from controller.phone_detail import PhoneDetailController
from data_classes.phone_detail import (
    BatteryDetail,
    DeviceInfoDetail,
    StorageDetail,
)
from layouts.flow_layout import FlowLayout
from models.phone_detail import PhoneDetailModel
from resources.paths import DashboardStyles
from resources.spacing import Spacing
from utils.app_state import app_state
from utils.styles import load_stylesheet
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

        self._controller: PhoneDetailController = PhoneDetailController(view=self, model=PhoneDetailModel(
            app_state.phone_repository))

        self._cards: List[InfoCard] = []

        self._setup_ui()
        self._setup_style()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        """Create all child widgets for the device status row."""
        for card in self._controller.fetch_phones_details():
            if isinstance(card, BatteryDetail):
                self._cards.append(self._create_battery(card))
            elif isinstance(card, StorageDetail):
                self._cards.append(self._create_storage(card))
            elif isinstance(card, DeviceInfoDetail):
                self._cards.append(self._create_device_info(card))

        for card in self._cards:
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )

    def _create_layout(self) -> None:
        """Create and configure the horizontal layout."""
        layout: FlowLayout = FlowLayout(min_width=self._card_width, parent=self)
        layout.setSpacing(Spacing.LG)

        for card in self._cards:
            layout.addWidget(card)

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

    def _create_device_info(self, info: DeviceInfoDetail) -> InfoCard:
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

    def _create_battery(self, battery: BatteryDetail) -> InfoCard:
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

    def _create_storage(self, storage: StorageDetail) -> InfoCard:
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

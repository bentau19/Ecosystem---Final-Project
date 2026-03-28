from enum import Enum, auto
from typing import List

from data_classes.phone_detail import (
    BasicPhoneDetail,
    DeviceInfoDetail,
    BatteryDetail,
    StorageDetail,
)

from resources.paths import Icons


class Item(Enum):
    DEVICE = auto()
    TYPE = auto()
    BATTERY = auto()
    STORAGE = auto()


class PhoneDetailRepository:
    def __init__(self):
        self._items: dict[Item, BasicPhoneDetail] = {
            Item.DEVICE: DeviceInfoDetail(
                title="Device",
                description="sqams",
                icon_path=Icons.SMARTPHONE,
                icon_background_color="#FFFFFF",
            ),
            Item.TYPE: DeviceInfoDetail(
                title="Type",
                description="android",
                icon_path=Icons.SMARTPHONE,
                icon_background_color="#FFFFFF",
            ),
            Item.BATTERY: BatteryDetail(
                title="Battery",
                icon_path=Icons.BATTERY,
                icon_background_color="#FFFFFF",
                battery_percentage=56,
                is_charging=False,
            ),
            Item.STORAGE: StorageDetail(
                title="Storage",
                icon_path=Icons.STORAGE,
                icon_background_color="#FFFFFF",
                used_storage=156,
                total_storage=256,
            ),
        }

    def update_item(
            self,
            item: Item,
            title: str = None,
            icon_path: str = None,
            icon_background_color: str = None,
            description: str = None,
            battery_percentage: int = None,
            is_charging: bool = None,
            storage_used: int = None,
            storage_total: int = None,
    ) -> None:
        if item not in self._items:
            raise ValueError(f"Item with title '{title}' does not exist.")

        current = self._items[item]

        if title is not None:
            current.title = title
        if icon_path is not None:
            current.icon_path = icon_path
        if icon_background_color is not None:
            current.icon_background_color = icon_background_color

        if isinstance(current, BatteryDetail):
            self._update_battery_detail(current, battery_percentage, is_charging)
        if isinstance(current, StorageDetail):
            self._update_storage_detail(current, storage_used, storage_total)
        if isinstance(current, DeviceInfoDetail):
            self._update_device_info_detail(current, description)

    def fetch_items(self) -> List[BasicPhoneDetail]:
        return list(self._items.values())

    @staticmethod
    def _update_device_info_detail(current: DeviceInfoDetail, description: str):
        if description is not None:
            current.description = description

    @staticmethod
    def _update_storage_detail(current: StorageDetail, storage_used, storage_total):
        if storage_used is not None:
            current.used_storage = storage_used
        if storage_total is not None:
            current.total_storage = storage_total

    @staticmethod
    def _update_battery_detail(current: BatteryDetail, battery_percentage, is_charging):
        if battery_percentage is not None:
            current.battery_percentage = battery_percentage
        if is_charging is not None:
            current.is_charging = is_charging

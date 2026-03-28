import pytest

from data_classes.phone_detail import BatteryDetail, StorageDetail, DeviceInfoDetail
from repositories.phone_detail import Item, PhoneDetailRepository


class TestPhoneDetailRepository:
    def setup_method(self):
        self.repo = PhoneDetailRepository()

    def test_fetch_returns_list(self):
        assert isinstance(self.repo.fetch_items(), list)

    def test_fetch_returns_four_items(self):
        assert len(self.repo.fetch_items()) == 4

    def test_fetch_has_battery(self):
        assert any(isinstance(i, BatteryDetail) for i in self.repo.fetch_items())

    def test_fetch_has_storage(self):
        assert any(isinstance(i, StorageDetail) for i in self.repo.fetch_items())

    def test_fetch_has_two_device_infos(self):
        infos = [i for i in self.repo.fetch_items() if isinstance(i, DeviceInfoDetail)]
        assert len(infos) == 2

    def test_update_title(self):
        self.repo.update_item(Item.DEVICE, title="MyPhone")
        assert self.repo._items[Item.DEVICE].title == "MyPhone"

    def test_update_icon_path(self):
        self.repo.update_item(Item.BATTERY, icon_path="new.png")
        assert self.repo._items[Item.BATTERY].icon_path == "new.png"

    def test_update_background_color(self):
        self.repo.update_item(Item.STORAGE, icon_background_color="#000000")
        assert self.repo._items[Item.STORAGE].icon_background_color == "#000000"

    def test_update_battery_percentage(self):
        self.repo.update_item(Item.BATTERY, battery_percentage=80)
        item = self.repo._items[Item.BATTERY]
        print(Item)
        if isinstance(item, BatteryDetail):
            assert item.battery_percentage == 80
        else:
            pytest.fail("Item is not a BatteryDetail")

    def test_update_battery_charging(self):
        self.repo.update_item(Item.BATTERY, is_charging=True)
        item = self.repo._items[Item.BATTERY]
        if isinstance(item, BatteryDetail):
            assert item.is_charging is True
        else:
            pytest.fail("Item is not a BatteryDetail")

    def test_update_battery_none_ignored(self):
        self.repo.update_item(Item.BATTERY, battery_percentage=None)
        item = self.repo._items[Item.BATTERY]
        if isinstance(item, BatteryDetail):
            assert item.battery_percentage == 56
        else:
            pytest.fail("Item is not a BatteryDetail")

    def test_update_storage_used(self):
        self.repo.update_item(Item.STORAGE, storage_used=64)
        item = self.repo._items[Item.STORAGE]
        if isinstance(item, StorageDetail):
            assert item.used_storage == 64
        else:
            pytest.fail("Item is not a StorageDetail")

    def test_update_storage_total(self):
        self.repo.update_item(Item.STORAGE, storage_total=512)
        item = self.repo._items[Item.STORAGE]
        if isinstance(item, StorageDetail):
            assert item.total_storage == 512
        else:
            pytest.fail("Item is not a StorageDetail")

    def test_update_device_description(self):
        self.repo.update_item(Item.DEVICE, description="Pixel 9")
        item = self.repo._items[Item.DEVICE]
        if isinstance(item, DeviceInfoDetail):
            assert item.description == "Pixel 9"
        else:
            pytest.fail("Item is not a DeviceInfoDetail")

    def test_update_invalid_item_raises(self):
        from typing import cast

        with pytest.raises(cast(tuple[type[BaseException], ...], (ValueError, KeyError))):
            self.repo.update_item("bad_key")

    def test_update_does_not_affect_other_items(self):
        self.repo.update_item(Item.BATTERY, battery_percentage=99)
        item = self.repo._items[Item.STORAGE]
        if isinstance(item, StorageDetail):
            assert item.used_storage == 156
        else:
            pytest.fail("Item is not a StorageDetail")

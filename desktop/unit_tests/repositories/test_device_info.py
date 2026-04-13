from typing import List
from unittest.mock import MagicMock

import pytest

from entities.device_info import DeviceStorageEntity, DeviceBatteryEntity, DeviceNameEntity
from enums.device_type import DeviceType
from repositories.device_info import DeviceInfoRepository
from stores.interfaces.base import IStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset the DeviceInfoRepository singleton before and after every test."""
    DeviceInfoRepository._instance = None
    DeviceInfoRepository._initialized = False
    yield
    DeviceInfoRepository._instance = None
    DeviceInfoRepository._initialized = False


@pytest.fixture()
def mock_store_empty() -> MagicMock:
    store: MagicMock = MagicMock(spec=IStore)
    store.load.return_value = {}
    return store


@pytest.fixture()
def mock_store_one_item(storage_entity: DeviceStorageEntity) -> MagicMock:
    store: MagicMock = MagicMock(spec=IStore)
    store.load.return_value = {DeviceType.STORAGE: storage_entity}
    return store


@pytest.fixture()
def mock_store_mult_items(
        battery_entity: DeviceBatteryEntity,
        storage_entity: DeviceStorageEntity,
        device_name_entity: DeviceNameEntity,
) -> MagicMock:
    store: MagicMock = MagicMock(spec=IStore)
    store.load.return_value = {
        DeviceType.BATTERY: battery_entity,
        DeviceType.STORAGE: storage_entity,
        DeviceType.NAME: device_name_entity,
    }
    return store


@pytest.fixture()
def all_stores(mock_store_empty: MagicMock, mock_store_one_item: MagicMock,
               mock_store_mult_items: MagicMock) -> List[MagicMock]:
    return [mock_store_empty, mock_store_one_item, mock_store_mult_items]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# --- load ---
def test_load_returns_store_data(all_stores: List[MagicMock]):
    for mock in all_stores:
        repo = DeviceInfoRepository(store=mock)
        assert repo.load() == mock.load.return_value


# --- get_by_id ---

def test_get_by_id_when_id_exists_returns_correct_entity(
        battery_entity: DeviceBatteryEntity,
        storage_entity: DeviceStorageEntity,
        device_name_entity: DeviceNameEntity,
):
    mock_store: MagicMock = MagicMock(spec=IStore)
    mock_store.load.return_value = {
        DeviceType.BATTERY: battery_entity,
        DeviceType.STORAGE: storage_entity,
        DeviceType.NAME: device_name_entity,
    }
    repo = DeviceInfoRepository(store=mock_store)

    assert repo.get_by_id(DeviceType.BATTERY) == battery_entity
    assert repo.get_by_id(DeviceType.STORAGE) == storage_entity
    assert repo.get_by_id(DeviceType.NAME) == device_name_entity


# --- get_all ---

def test_get_all_returns_list_of_all_stored_entities(all_stores: List[MagicMock]):
    for mock in all_stores:
        repo = DeviceInfoRepository(store=mock)
        assert repo.get_all() == list(mock.load.return_value.values())


# --- save ---

def test_save_new_entity_makes_it_retrievable_by_id(
        mock_store_empty: MagicMock,
        battery_entity: DeviceBatteryEntity,
        storage_entity: DeviceStorageEntity,
):
    repo = DeviceInfoRepository(store=mock_store_empty)

    repo.save(battery_entity)
    assert repo.get_by_id(DeviceType.BATTERY) == battery_entity

    repo.save(storage_entity)
    assert repo.get_by_id(DeviceType.STORAGE) == storage_entity


def test_save_existing_entity_overwrites_previous_value(
        mock_store_empty: MagicMock,
        storage_entity: DeviceStorageEntity,
):
    repo = DeviceInfoRepository(store=mock_store_empty)
    repo.save(storage_entity)

    storage_entity.title = "xyz"
    repo.save(storage_entity)

    item = repo.get_by_id(DeviceType.STORAGE)

    assert item is not None
    assert item.title == "xyz"


# --- delete ---

def test_delete_existing_entity_returns_none_on_get(
        mock_store_empty: MagicMock,
        battery_entity: DeviceBatteryEntity,
        storage_entity: DeviceStorageEntity,
):
    mock_store_empty.load.return_value = {
        DeviceType.BATTERY: battery_entity,
        DeviceType.STORAGE: storage_entity,
    }
    repo = DeviceInfoRepository(store=mock_store_empty)

    repo.delete(DeviceType.BATTERY)
    assert repo.get_by_id(DeviceType.BATTERY) is None

    repo.delete(DeviceType.STORAGE)
    assert repo.get_by_id(DeviceType.STORAGE) is None


def test_delete_all_entities_results_in_empty_repo(
        mock_store_empty: MagicMock,
        battery_entity: DeviceBatteryEntity,
        storage_entity: DeviceStorageEntity,
):
    mock_store_empty.load.return_value = {
        DeviceType.BATTERY: battery_entity,
        DeviceType.STORAGE: storage_entity,
    }
    repo = DeviceInfoRepository(store=mock_store_empty)

    repo.delete(DeviceType.BATTERY)
    repo.delete(DeviceType.STORAGE)

    assert len(repo.get_all()) == 0

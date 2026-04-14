"""Unit tests for CurrentDeviceInfoRepository."""

from unittest.mock import MagicMock

import pytest

from entities.device_info import DeviceInfoEntity
from repositories.device import DeviceRepository
from stores.interfaces.base import IStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def entity() -> DeviceInfoEntity:
    return DeviceInfoEntity(
        id="dev-001",
        name="Pixel 8 Pro",
        os="Android 14",
        tag="Work",
        last_seen="now",
        battery_level=82,
        battery_charging=True,
        storage_used=64,
        storage_total=128,
        ip="192.168.1.10",
    )


@pytest.fixture()
def other_entity() -> DeviceInfoEntity:
    return DeviceInfoEntity(
        id="dev-002",
        name="Galaxy S24",
        os="Android 14",
        tag="Home",
        last_seen="today",
        battery_level=45,
        battery_charging=False,
        storage_used=110,
        storage_total=256,
        ip="192.168.1.11",
    )


@pytest.fixture()
def mock_store_empty() -> MagicMock:
    store: MagicMock = MagicMock(spec=IStore)
    store.load.return_value = None
    return store


@pytest.fixture()
def mock_store_with_device(entity: DeviceInfoEntity) -> MagicMock:
    store: MagicMock = MagicMock(spec=IStore)
    store.load.return_value = entity
    return store


@pytest.fixture()
def repo_empty(mock_store_empty: MagicMock) -> DeviceRepository:
    return DeviceRepository(store=mock_store_empty)


@pytest.fixture()
def repo_with_device(mock_store_with_device: MagicMock) -> DeviceRepository:
    return DeviceRepository(store=mock_store_with_device)


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_constructor_loads_from_store_on_init(mock_store_with_device: MagicMock) -> None:
    DeviceRepository(store=mock_store_with_device)

    mock_store_with_device.load.assert_called_once()


# ---------------------------------------------------------------------------
# get_current
# ---------------------------------------------------------------------------


def test_get_current_returns_none_when_no_device(
    repo_empty: DeviceRepository,
) -> None:
    assert repo_empty.get_current() is None


def test_get_current_returns_entity_when_device_exists(
    repo_with_device: DeviceRepository,
    entity: DeviceInfoEntity,
) -> None:
    assert repo_with_device.get_current() == entity


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


def test_get_by_id_returns_entity_when_id_matches(
    repo_with_device: DeviceRepository,
    entity: DeviceInfoEntity,
) -> None:
    assert repo_with_device.get_by_id("dev-001") == entity


def test_get_by_id_returns_none_when_id_does_not_match(
    repo_with_device: DeviceRepository,
) -> None:
    assert repo_with_device.get_by_id("dev-999") is None


def test_get_by_id_returns_none_when_no_device(
    repo_empty: DeviceRepository,
) -> None:
    assert repo_empty.get_by_id("dev-001") is None


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


def test_get_all_returns_empty_list_when_no_device(
    repo_empty: DeviceRepository,
) -> None:
    assert repo_empty.get_all() == []


def test_get_all_returns_single_element_list_when_device_exists(
    repo_with_device: DeviceRepository,
    entity: DeviceInfoEntity,
) -> None:
    result = repo_with_device.get_all()

    assert len(result) == 1
    assert result[0] == entity


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


def test_save_stores_entity_as_current_device(
    repo_empty: DeviceRepository,
    entity: DeviceInfoEntity,
) -> None:
    repo_empty.save(entity)

    assert repo_empty.get_current() == entity


def test_save_overwrites_previously_stored_device(
    repo_with_device: DeviceRepository,
    other_entity: DeviceInfoEntity,
) -> None:
    repo_with_device.save(other_entity)

    assert repo_with_device.get_current() == other_entity


def test_save_calls_store_save(
    repo_empty: DeviceRepository,
    mock_store_empty: MagicMock,
    entity: DeviceInfoEntity,
) -> None:
    repo_empty.save(entity)

    mock_store_empty.save.assert_called_once_with(entity)


def test_save_emits_entity_saved_with_correct_entity(
    repo_empty: DeviceRepository,
    entity: DeviceInfoEntity,
) -> None:
    received: list[DeviceInfoEntity] = []
    repo_empty.entity_saved.connect(lambda e: received.append(e))

    repo_empty.save(entity)

    assert received == [entity]


def test_save_makes_entity_appear_in_get_all(
    repo_empty: DeviceRepository,
    entity: DeviceInfoEntity,
) -> None:
    repo_empty.save(entity)

    assert entity in repo_empty.get_all()


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_matching_id_clears_current_device(
    repo_with_device: DeviceRepository,
) -> None:
    repo_with_device.delete("dev-001")

    assert repo_with_device.get_current() is None


def test_delete_matching_id_calls_store_save_with_none(
    repo_with_device: DeviceRepository,
    mock_store_with_device: MagicMock,
) -> None:
    repo_with_device.delete("dev-001")

    mock_store_with_device.save.assert_called_once_with(None)


def test_delete_matching_id_emits_entity_deleted(
    repo_with_device: DeviceRepository,
) -> None:
    received: list[str] = []
    repo_with_device.entity_deleted.connect(lambda id: received.append(id))

    repo_with_device.delete("dev-001")

    assert received == ["dev-001"]


def test_delete_non_matching_id_does_not_clear_device(
    repo_with_device: DeviceRepository,
    entity: DeviceInfoEntity,
) -> None:
    repo_with_device.delete("dev-999")

    assert repo_with_device.get_current() == entity


def test_delete_non_matching_id_still_emits_entity_deleted(
    repo_with_device: DeviceRepository,
) -> None:
    received: list[str] = []
    repo_with_device.entity_deleted.connect(lambda id: received.append(id))

    repo_with_device.delete("dev-999")

    assert received == ["dev-999"]


def test_delete_when_no_device_still_emits_entity_deleted(
    repo_empty: DeviceRepository,
) -> None:
    received: list[str] = []
    repo_empty.entity_deleted.connect(lambda id: received.append(id))

    repo_empty.delete("dev-001")

    assert received == ["dev-001"]

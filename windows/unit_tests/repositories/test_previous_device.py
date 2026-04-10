"""Unit tests for PreviousDeviceRepository."""

from unittest.mock import MagicMock

import pytest

from entities.previous_device import PreviousDeviceEntity
from repositories.previous_device import PreviousDeviceRepository
from stores.interfaces.base import IStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_store_empty() -> MagicMock:
    store: MagicMock = MagicMock(spec=IStore)
    store.load.return_value = {}
    return store


@pytest.fixture()
def mock_store_one_item(previous_device_online: PreviousDeviceEntity) -> MagicMock:
    store: MagicMock = MagicMock(spec=IStore)
    store.load.return_value = {"dev-001": previous_device_online}
    return store


@pytest.fixture()
def mock_store_mult_items(
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
) -> MagicMock:
    store: MagicMock = MagicMock(spec=IStore)
    store.load.return_value = {
        "dev-001": previous_device_online,
        "dev-002": previous_device_recent,
        "dev-003": previous_device_idle,
    }
    return store


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def test_load_on_empty_store_returns_empty_dict(mock_store_empty: MagicMock) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)

    assert repo.load() == {}


def test_load_returns_all_devices_from_store(
    mock_store_mult_items: MagicMock,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_mult_items)

    result = repo.load()

    assert result == {
        "dev-001": previous_device_online,
        "dev-002": previous_device_recent,
        "dev-003": previous_device_idle,
    }


def test_load_reloads_fresh_data_from_store(mock_store_empty: MagicMock) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)
    repo.load()
    repo.load()

    # store.load called once on construction + twice explicitly
    assert mock_store_empty.load.call_count == 3


def test_constructor_eagerly_loads_from_store(mock_store_mult_items: MagicMock) -> None:
    PreviousDeviceRepository(store=mock_store_mult_items)

    mock_store_mult_items.load.assert_called_once()


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


def test_get_by_id_returns_correct_entity_when_id_exists(
    mock_store_mult_items: MagicMock,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_mult_items)

    assert repo.get_by_id("dev-001") == previous_device_online
    assert repo.get_by_id("dev-002") == previous_device_recent
    assert repo.get_by_id("dev-003") == previous_device_idle


def test_get_by_id_returns_none_when_id_does_not_exist(mock_store_empty: MagicMock) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)

    assert repo.get_by_id("nonexistent") is None


def test_get_by_id_returns_none_after_all_devices_deleted(
    mock_store_mult_items: MagicMock,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_mult_items)

    repo.delete("dev-001")
    repo.delete("dev-002")
    repo.delete("dev-003")

    assert repo.get_by_id("dev-001") is None
    assert repo.get_by_id("dev-002") is None
    assert repo.get_by_id("dev-003") is None


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


def test_get_all_on_empty_store_returns_empty_list(mock_store_empty: MagicMock) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)

    assert repo.get_all() == []


def test_get_all_returns_list_of_all_entities(
    mock_store_mult_items: MagicMock,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_mult_items)

    result = repo.get_all()

    assert len(result) == 3
    assert previous_device_online in result
    assert previous_device_recent in result
    assert previous_device_idle in result


def test_get_all_returns_single_entity_list(
    mock_store_one_item: MagicMock,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_one_item)

    result = repo.get_all()

    assert result == [previous_device_online]


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


def test_save_new_entity_makes_it_retrievable_by_id(
    mock_store_empty: MagicMock,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)

    repo.save(previous_device_online)

    assert repo.get_by_id("dev-001") == previous_device_online


def test_save_new_entity_appears_in_get_all(
    mock_store_empty: MagicMock,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)

    repo.save(previous_device_online)
    repo.save(previous_device_recent)

    result = repo.get_all()
    assert previous_device_online in result
    assert previous_device_recent in result


def test_save_existing_entity_overwrites_previous_value(
    mock_store_empty: MagicMock,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)
    repo.save(previous_device_online)

    previous_device_online.name = "Updated Name"
    repo.save(previous_device_online)

    assert repo.get_by_id("dev-001").name == "Updated Name"


def test_save_calls_store_save(
    mock_store_empty: MagicMock,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)

    repo.save(previous_device_online)

    mock_store_empty.save.assert_called_once()


def test_save_emits_device_saved_signal(
    mock_store_empty: MagicMock,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)
    received: list[PreviousDeviceEntity] = []
    repo.device_saved.connect(lambda entity: received.append(entity))

    repo.save(previous_device_online)

    assert len(received) == 1
    assert received[0] == previous_device_online


def test_save_emits_device_saved_signal_with_correct_entity(
    mock_store_empty: MagicMock,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)
    received: list[PreviousDeviceEntity] = []
    repo.device_saved.connect(lambda entity: received.append(entity))

    repo.save(previous_device_online)
    repo.save(previous_device_recent)

    assert received[0] == previous_device_online
    assert received[1] == previous_device_recent


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_existing_entity_makes_it_unretrievable(
    mock_store_mult_items: MagicMock,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_mult_items)

    repo.delete("dev-001")

    assert repo.get_by_id("dev-001") is None


def test_delete_existing_entity_removes_it_from_get_all(
    mock_store_mult_items: MagicMock,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_mult_items)

    repo.delete("dev-001")

    assert previous_device_online not in repo.get_all()


def test_delete_all_entities_results_in_empty_repo(
    mock_store_mult_items: MagicMock,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_mult_items)

    repo.delete("dev-001")
    repo.delete("dev-002")
    repo.delete("dev-003")

    assert repo.get_all() == []


def test_delete_existing_entity_calls_store_save(
    mock_store_mult_items: MagicMock,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_mult_items)

    repo.delete("dev-001")

    mock_store_mult_items.save.assert_called_once()


def test_delete_nonexistent_id_does_not_call_store_save(
    mock_store_empty: MagicMock,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)

    repo.delete("nonexistent")

    mock_store_empty.save.assert_not_called()


def test_delete_emits_device_deleted_signal_when_entity_exists(
    mock_store_mult_items: MagicMock,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_mult_items)
    received: list[str] = []
    repo.device_deleted.connect(lambda id: received.append(id))

    repo.delete("dev-001")

    assert received == ["dev-001"]


def test_delete_emits_device_deleted_signal_even_when_id_absent(
    mock_store_empty: MagicMock,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_empty)
    received: list[str] = []
    repo.device_deleted.connect(lambda id: received.append(id))

    repo.delete("nonexistent")

    assert received == ["nonexistent"]


def test_delete_emits_correct_id_in_signal(
    mock_store_mult_items: MagicMock,
) -> None:
    repo = PreviousDeviceRepository(store=mock_store_mult_items)
    received: list[str] = []
    repo.device_deleted.connect(lambda id: received.append(id))

    repo.delete("dev-002")
    repo.delete("dev-003")

    assert received == ["dev-002", "dev-003"]

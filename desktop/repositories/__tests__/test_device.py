"""Unit tests for DeviceRepository (SQLite-backed)."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from domain.entities.device_info import DeviceEntity
from repositories.device import DeviceRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
#
#

@pytest.fixture()
def entity() -> DeviceEntity:
    return DeviceEntity(
        id="dev-001",
        name="Pixel 8 Pro",
        os="Android 14",
        tag="Work",
        last_connected=date(2024, 1, 15),
        battery_level=82,
        battery_charging=True,
        storage_used=64,
        storage_total=128,
        ip="192.168.1.10",
    )


@pytest.fixture()
def other_entity() -> DeviceEntity:
    return DeviceEntity(
        id="dev-002",
        name="Galaxy S24",
        os="Android 14",
        tag="Home",
        last_connected=date(2024, 1, 14),
        battery_level=45,
        battery_charging=False,
        storage_used=110,
        storage_total=256,
        ip="192.168.1.11",
    )


@pytest.fixture()
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DeviceRepository:
    """Provide a DeviceRepository backed by a temp SQLite database.

    Monkeypatches sqlite3.connect so all calls within DeviceRepository are
    redirected to a fresh database in tmp_path instead of the production file.
    """
    db_path = str(tmp_path / "test_devices.db")
    original_connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda path, **kw: original_connect(db_path, **kw))
    return DeviceRepository()


# ---------------------------------------------------------------------------
# id_exists
# ---------------------------------------------------------------------------


def test_id_exists_returns_false_when_db_is_empty(repository: DeviceRepository) -> None:
    assert repository.id_exists("dev-001") is False


def test_id_exists_returns_true_after_save(
    repository: DeviceRepository,
    entity: DeviceEntity,
) -> None:
    repository.save(entity)

    assert repository.id_exists("dev-001") is True


def test_id_exists_returns_false_for_unknown_id_when_other_entities_exist(
    repository: DeviceRepository,
    entity: DeviceEntity,
) -> None:
    repository.save(entity)

    assert repository.id_exists("dev-999") is False


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


def test_get_by_id_returns_none_when_db_is_empty(repository: DeviceRepository) -> None:
    assert repository.get_by_id("dev-001") is None


def test_get_by_id_returns_entity_after_save(
    repository: DeviceRepository,
    entity: DeviceEntity,
) -> None:
    repository.save(entity)

    result = repository.get_by_id("dev-001")

    assert result == entity


def test_get_by_id_returns_none_when_id_does_not_match(
    repository: DeviceRepository,
    entity: DeviceEntity,
) -> None:
    repository.save(entity)

    assert repository.get_by_id("dev-999") is None


def test_get_by_id_returns_correct_entity_when_multiple_saved(
    repository: DeviceRepository,
    entity: DeviceEntity,
    other_entity: DeviceEntity,
) -> None:
    repository.save(entity)
    repository.save(other_entity)

    assert repository.get_by_id("dev-001") == entity
    assert repository.get_by_id("dev-002") == other_entity


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


def test_get_all_returns_empty_list_when_db_is_empty(repository: DeviceRepository) -> None:
    assert repository.get_all() == []


def test_get_all_returns_single_entity_after_one_save(
    repository: DeviceRepository,
    entity: DeviceEntity,
) -> None:
    repository.save(entity)

    result = repository.get_all()

    assert len(result) == 1
    assert result[0] == entity


def test_get_all_returns_all_saved_entities(
    repository: DeviceRepository,
    entity: DeviceEntity,
    other_entity: DeviceEntity,
) -> None:
    repository.save(entity)
    repository.save(other_entity)

    result = repository.get_all()

    assert len(result) == 2
    assert entity in result
    assert other_entity in result


def test_get_all_excludes_deleted_entities(
    repository: DeviceRepository,
    entity: DeviceEntity,
    other_entity: DeviceEntity,
) -> None:
    repository.save(entity)
    repository.save(other_entity)

    repository.delete("dev-001")

    result = repository.get_all()
    assert len(result) == 1
    assert entity not in result


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


def test_save_persists_entity_to_db(
    repository: DeviceRepository,
    entity: DeviceEntity,
) -> None:
    repository.save(entity)

    assert repository.get_by_id("dev-001") == entity


def test_save_replaces_existing_entity_with_same_id(
    repository: DeviceRepository,
    entity: DeviceEntity,
) -> None:
    repository.save(entity)

    updated = DeviceEntity(
        id="dev-001",
        name="Updated Name",
        os="Android 15",
        tag="Work",
        last_connected=date(2024, 3, 10),
        battery_level=50,
        battery_charging=False,
        storage_used=32,
        storage_total=64,
        ip="10.0.0.1",
    )
    repository.save(updated)

    assert repository.get_by_id("dev-001").name == "Updated Name"


def test_save_emits_entity_saved_with_saved_entity(
    repository: DeviceRepository,
    entity: DeviceEntity,
) -> None:
    received: list[DeviceEntity] = []
    repository.entity_saved.connect(lambda e: received.append(e))

    repository.save(entity)

    assert received == [entity]


def test_save_emits_entity_saved_once_per_call(
    repository: DeviceRepository,
    entity: DeviceEntity,
    other_entity: DeviceEntity,
) -> None:
    received: list[DeviceEntity] = []
    repository.entity_saved.connect(lambda e: received.append(e))

    repository.save(entity)
    repository.save(other_entity)

    assert len(received) == 2
    assert received[0] == entity
    assert received[1] == other_entity


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_removes_entity_from_db(
    repository: DeviceRepository,
    entity: DeviceEntity,
) -> None:
    repository.save(entity)

    repository.delete("dev-001")

    assert repository.get_by_id("dev-001") is None


def test_delete_only_removes_matching_entity(
    repository: DeviceRepository,
    entity: DeviceEntity,
    other_entity: DeviceEntity,
) -> None:
    repository.save(entity)
    repository.save(other_entity)

    repository.delete("dev-001")

    assert repository.get_by_id("dev-002") == other_entity


def test_delete_emits_entity_deleted_signal(
    repository: DeviceRepository,
    entity: DeviceEntity,
) -> None:
    repository.save(entity)
    received: list[str] = []
    repository.entity_deleted.connect(lambda id_: received.append(id_))

    repository.delete("dev-001")

    assert received == ["dev-001"]


def test_delete_nonexistent_id_still_emits_entity_deleted(
    repository: DeviceRepository,
) -> None:
    received: list[str] = []
    repository.entity_deleted.connect(lambda id_: received.append(id_))

    repository.delete("dev-999")

    assert received == ["dev-999"]


def test_delete_all_entities_results_in_empty_repo(
    repository: DeviceRepository,
    entity: DeviceEntity,
    other_entity: DeviceEntity,
) -> None:
    repository.save(entity)
    repository.save(other_entity)

    repository.delete("dev-001")
    repository.delete("dev-002")

    assert repository.get_all() == []

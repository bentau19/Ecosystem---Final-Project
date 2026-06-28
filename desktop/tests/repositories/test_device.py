"""Unit tests for DeviceRepository (JSON-backed, single current device)."""

from datetime import date
from pathlib import Path

import pytest

from domain.entities.device_info import DeviceEntity
from repositories.device import DeviceRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
        storage_used=64.0,
        storage_total=128.0,
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
        storage_used=110.0,
        storage_total=256.0,
        ip="192.168.1.11",
    )


@pytest.fixture()
def repository(tmp_path: Path) -> DeviceRepository:
    """Provide a DeviceRepository backed by a temp ``device.json`` in tmp_path."""
    return DeviceRepository(path=tmp_path / "device.json")


# ---------------------------------------------------------------------------
# id_exists
# ---------------------------------------------------------------------------


def test_id_exists_returns_false_when_empty(repository: DeviceRepository) -> None:
    assert repository.id_exists("dev-001") is False


def test_id_exists_returns_true_after_save(
    repository: DeviceRepository, entity: DeviceEntity
) -> None:
    repository.save(entity)

    assert repository.id_exists("dev-001") is True


def test_id_exists_returns_false_for_unknown_id(
    repository: DeviceRepository, entity: DeviceEntity
) -> None:
    repository.save(entity)

    assert repository.id_exists("dev-999") is False


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


def test_get_by_id_returns_none_when_empty(repository: DeviceRepository) -> None:
    assert repository.get_by_id("dev-001") is None


def test_get_by_id_returns_entity_after_save(
    repository: DeviceRepository, entity: DeviceEntity
) -> None:
    repository.save(entity)

    assert repository.get_by_id("dev-001") == entity


def test_get_by_id_returns_none_when_id_does_not_match(
    repository: DeviceRepository, entity: DeviceEntity
) -> None:
    repository.save(entity)

    assert repository.get_by_id("dev-999") is None


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


def test_get_all_returns_empty_list_when_empty(repository: DeviceRepository) -> None:
    assert repository.get_all() == []


def test_get_all_returns_single_entity_after_save(
    repository: DeviceRepository, entity: DeviceEntity
) -> None:
    repository.save(entity)

    assert repository.get_all() == [entity]


# ---------------------------------------------------------------------------
# save (single-device: a new save replaces the previous device)
# ---------------------------------------------------------------------------


def test_save_persists_entity(
    repository: DeviceRepository, entity: DeviceEntity
) -> None:
    repository.save(entity)

    assert repository.get_by_id("dev-001") == entity


def test_save_replaces_previous_device(
    repository: DeviceRepository, entity: DeviceEntity, other_entity: DeviceEntity
) -> None:
    repository.save(entity)
    repository.save(other_entity)

    # Only the most recently saved device is retained.
    assert repository.get_by_id("dev-001") is None
    assert repository.get_by_id("dev-002") == other_entity
    assert repository.get_all() == [other_entity]


def test_save_replaces_existing_device_with_same_id(
    repository: DeviceRepository, entity: DeviceEntity
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
        storage_used=32.0,
        storage_total=64.0,
        ip="10.0.0.1",
    )
    repository.save(updated)

    assert repository.get_by_id("dev-001").name == "Updated Name"


def test_save_emits_entity_saved_with_saved_entity(
    repository: DeviceRepository, entity: DeviceEntity
) -> None:
    received: list[DeviceEntity] = []
    repository.entity_saved.connect(lambda e: received.append(e))

    repository.save(entity)

    assert received == [entity]


def test_save_emits_entity_saved_once_per_call(
    repository: DeviceRepository, entity: DeviceEntity, other_entity: DeviceEntity
) -> None:
    received: list[DeviceEntity] = []
    repository.entity_saved.connect(lambda e: received.append(e))

    repository.save(entity)
    repository.save(other_entity)

    assert received == [entity, other_entity]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_removes_current_device(
    repository: DeviceRepository, entity: DeviceEntity
) -> None:
    repository.save(entity)

    repository.delete("dev-001")

    assert repository.get_by_id("dev-001") is None
    assert repository.get_all() == []


def test_delete_non_matching_id_keeps_current_device(
    repository: DeviceRepository, entity: DeviceEntity
) -> None:
    repository.save(entity)

    repository.delete("dev-999")

    assert repository.get_by_id("dev-001") == entity


def test_delete_emits_entity_deleted_signal(
    repository: DeviceRepository, entity: DeviceEntity
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


# ---------------------------------------------------------------------------
# Persistence across instances
# ---------------------------------------------------------------------------


def test_saved_device_persists_to_a_new_repository(
    tmp_path: Path, entity: DeviceEntity
) -> None:
    path = tmp_path / "device.json"
    repo = DeviceRepository(path=path)
    repo.save(entity)

    reloaded = DeviceRepository(path=path)
    assert reloaded.get_by_id("dev-001") == entity

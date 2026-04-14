"""Unit tests for DeviceInfoViewModel."""

from unittest.mock import MagicMock, patch

import pytest

from dto.device_info import (
    DeviceBatteryDTO,
    DeviceNameDTO,
    DeviceOSDTO,
    DeviceStorageDTO,
)
from entities.device_info import DeviceInfoEntity
from viewmodels.device import DeviceViewModel


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
def mock_repo() -> MagicMock:
    repo: MagicMock = MagicMock()
    repo.entity_saved.connect = MagicMock()
    return repo


@pytest.fixture()
def view_model(mock_repo: MagicMock) -> DeviceViewModel:
    with (
        patch("viewmodels.current_device_info.repository_manager") as mock_rm,
        patch("viewmodels.current_device_info.services_manager"),
    ):
        mock_rm.current_device_info_repository = mock_repo
        vm = DeviceViewModel()
    return vm


# ---------------------------------------------------------------------------
# load_device_infos
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# _on_entity_saved
# ---------------------------------------------------------------------------


def test_on_entity_saved_emits_device_infos_updated(
    view_model: DeviceViewModel,
    entity: DeviceInfoEntity,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.append(dtos))

    view_model._on_entity_saved(entity)

    assert len(received) == 1


def test_on_entity_saved_emits_four_dtos(
    view_model: DeviceViewModel,
    entity: DeviceInfoEntity,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_entity_saved(entity)

    assert len(received) == 4


def test_on_entity_saved_battery_dto_fields_match_entity(
    view_model: DeviceViewModel,
    entity: DeviceInfoEntity,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_entity_saved(entity)

    battery_dto = next(dto for dto in received if isinstance(dto, DeviceBatteryDTO))
    assert battery_dto.level == entity.battery_level
    assert battery_dto.is_charging == entity.battery_charging


def test_on_entity_saved_storage_dto_fields_match_entity(
    view_model: DeviceViewModel,
    entity: DeviceInfoEntity,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_entity_saved(entity)

    storage_dto = next(dto for dto in received if isinstance(dto, DeviceStorageDTO))
    assert storage_dto.used == entity.storage_used
    assert storage_dto.total == entity.storage_total


# ---------------------------------------------------------------------------
# _to_dtos (static helper)
# ---------------------------------------------------------------------------


def test_to_dtos_returns_four_items(entity: DeviceInfoEntity) -> None:
    assert len(DeviceViewModel._to_dtos(entity)) == 4


def test_to_dtos_first_item_is_name_dto(entity: DeviceInfoEntity) -> None:
    result = DeviceViewModel._to_dtos(entity)

    assert isinstance(result[0], DeviceNameDTO)
    assert result[0].name == entity.name


def test_to_dtos_second_item_is_os_dto(entity: DeviceInfoEntity) -> None:
    result = DeviceViewModel._to_dtos(entity)

    assert isinstance(result[1], DeviceOSDTO)
    assert result[1].os == entity.os


def test_to_dtos_third_item_is_battery_dto(entity: DeviceInfoEntity) -> None:
    result = DeviceViewModel._to_dtos(entity)

    assert isinstance(result[2], DeviceBatteryDTO)
    assert result[2].level == entity.battery_level
    assert result[2].is_charging == entity.battery_charging


def test_to_dtos_fourth_item_is_storage_dto(entity: DeviceInfoEntity) -> None:
    result = DeviceViewModel._to_dtos(entity)

    assert isinstance(result[3], DeviceStorageDTO)
    assert result[3].used == entity.storage_used
    assert result[3].total == entity.storage_total

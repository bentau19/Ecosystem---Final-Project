"""Unit tests for DeviceViewModel — current-device info methods."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from domain.dto.device_info import (
    DeviceBatteryDTO,
    DeviceNameDTO,
    DeviceOSDTO,
    DeviceStorageDTO,
)
from domain.entities.device_info import DeviceEntity
from viewmodels.device import DeviceViewModel


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
        storage_used=64,
        storage_total=128,
        ip="192.168.1.10",
    )


@pytest.fixture()
def mock_connectivity() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def mock_device_info_service() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def view_model(
    qtbot,
    mock_connectivity: MagicMock,
    mock_device_info_service: MagicMock,
) -> DeviceViewModel:
    return DeviceViewModel(
        connectivity_service=mock_connectivity,
        device_info_service=mock_device_info_service,
    )


# ---------------------------------------------------------------------------
# load_device_info / _on_device_fetched
# ---------------------------------------------------------------------------


def test_load_device_info_calls_fetch_device_by_id_with_current_id(
    view_model: DeviceViewModel,
    mock_device_info_service: MagicMock,
) -> None:
    view_model.load_device_info()

    mock_device_info_service.fetch_device_by_id.assert_called_with(
        view_model._current_device_connected_id
    )


def test_on_device_fetched_emits_device_infos_updated_when_entity_found(
    view_model: DeviceViewModel,
    entity: DeviceEntity,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.append(dtos))

    view_model._on_device_fetched(entity)

    assert len(received) == 1


def test_on_device_fetched_does_not_emit_when_entity_is_none(
    view_model: DeviceViewModel,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.append(dtos))

    view_model._on_device_fetched(None)

    assert received == []


def test_on_device_fetched_emits_four_dtos(
    view_model: DeviceViewModel,
    entity: DeviceEntity,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_device_fetched(entity)

    assert len(received) == 4


# ---------------------------------------------------------------------------
# _on_entity_saved
# ---------------------------------------------------------------------------


def test_on_entity_saved_emits_device_infos_updated(
    view_model: DeviceViewModel,
    entity: DeviceEntity,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.append(dtos))

    view_model._on_entity_saved(entity)

    assert len(received) == 1


def test_on_entity_saved_emits_four_dtos(
    view_model: DeviceViewModel,
    entity: DeviceEntity,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_entity_saved(entity)

    assert len(received) == 4


def test_on_entity_saved_battery_dto_fields_match_entity(
    view_model: DeviceViewModel,
    entity: DeviceEntity,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_entity_saved(entity)

    battery_dto = next(dto for dto in received if isinstance(dto, DeviceBatteryDTO))
    assert battery_dto.level == entity.battery_level
    assert battery_dto.is_charging == entity.battery_charging


def test_on_entity_saved_storage_dto_fields_match_entity(
    view_model: DeviceViewModel,
    entity: DeviceEntity,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_entity_saved(entity)

    storage_dto = next(dto for dto in received if isinstance(dto, DeviceStorageDTO))
    assert storage_dto.used == entity.storage_used
    assert storage_dto.total == entity.storage_total


# ---------------------------------------------------------------------------
# _on_device_info_ready
# ---------------------------------------------------------------------------


def test_on_device_info_ready_does_not_save_again(
    view_model: DeviceViewModel,
    mock_device_info_service: MagicMock,
    entity: DeviceEntity,
) -> None:
    # DeviceInfoService already persists the entity before emitting device_info_ready;
    # the VM slot must not call save a second time.
    mock_device_info_service.save.reset_mock()   # clear the call made in __init__
    view_model._on_device_info_ready(entity)

    mock_device_info_service.save.assert_not_called()


def test_on_device_info_ready_updates_current_connected_id(
    view_model: DeviceViewModel,
    entity: DeviceEntity,
) -> None:
    view_model._on_device_info_ready(entity)

    assert view_model._current_device_connected_id == entity.id


def test_on_device_info_ready_emits_device_infos_updated(
    view_model: DeviceViewModel,
    entity: DeviceEntity,
) -> None:
    received: list = []
    view_model.device_infos_updated.connect(lambda dtos: received.append(dtos))

    view_model._on_device_info_ready(entity)

    assert len(received) == 1


# ---------------------------------------------------------------------------
# _to_device_info_dtos (static helper)
# ---------------------------------------------------------------------------


def test_to_device_info_dtos_returns_four_items(entity: DeviceEntity) -> None:
    assert len(DeviceViewModel._to_device_info_dtos(entity)) == 4


def test_to_device_info_dtos_first_item_is_name_dto(entity: DeviceEntity) -> None:
    result = DeviceViewModel._to_device_info_dtos(entity)

    assert isinstance(result[0], DeviceNameDTO)
    assert result[0].name == entity.name


def test_to_device_info_dtos_second_item_is_os_dto(entity: DeviceEntity) -> None:
    result = DeviceViewModel._to_device_info_dtos(entity)

    assert isinstance(result[1], DeviceOSDTO)
    assert result[1].os == entity.os


def test_to_device_info_dtos_third_item_is_battery_dto(entity: DeviceEntity) -> None:
    result = DeviceViewModel._to_device_info_dtos(entity)

    assert isinstance(result[2], DeviceBatteryDTO)
    assert result[2].level == entity.battery_level
    assert result[2].is_charging == entity.battery_charging


def test_to_device_info_dtos_fourth_item_is_storage_dto(entity: DeviceEntity) -> None:
    result = DeviceViewModel._to_device_info_dtos(entity)

    assert isinstance(result[3], DeviceStorageDTO)
    assert result[3].used == entity.storage_used
    assert result[3].total == entity.storage_total

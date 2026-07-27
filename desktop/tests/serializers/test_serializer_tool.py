"""Unit tests for ToolSerializer (JSON dict ↔ ToolEntity)."""

import pytest

from domain.entities.tool import ToolEntity
from serializers.tool import ToolSerializer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def serializer() -> ToolSerializer:
    return ToolSerializer()


@pytest.fixture()
def tool_enabled() -> ToolEntity:
    return ToolEntity(
        title="hammer",
        description="A tool for driving nails into wood.",
        icon_path="hammer.png",
        is_enabled=True,
    )


@pytest.fixture()
def tool_disabled() -> ToolEntity:
    return ToolEntity(
        title="screwdriver",
        description="A tool for driving screws.",
        icon_path="screwdriver.png",
        is_enabled=False,
    )


# ---------------------------------------------------------------------------
# serialize
# ---------------------------------------------------------------------------


def test_serialize_returns_none_for_none_entity(serializer: ToolSerializer) -> None:
    assert serializer.serialize(None) is None


def test_serialize_returns_dict(serializer: ToolSerializer, tool_enabled: ToolEntity) -> None:
    assert isinstance(serializer.serialize(tool_enabled), dict)


def test_serialize_has_expected_keys(serializer: ToolSerializer, tool_enabled: ToolEntity) -> None:
    assert set(serializer.serialize(tool_enabled)) == {
        "title",
        "description",
        "icon_path",
        "is_enabled",
    }


def test_serialize_maps_fields(serializer: ToolSerializer, tool_enabled: ToolEntity) -> None:
    data = serializer.serialize(tool_enabled)
    assert data["title"] == tool_enabled.title
    assert data["description"] == tool_enabled.description
    assert data["icon_path"] == tool_enabled.icon_path
    assert data["is_enabled"] is True


def test_serialize_maps_is_enabled_false(serializer: ToolSerializer, tool_disabled: ToolEntity) -> None:
    assert serializer.serialize(tool_disabled)["is_enabled"] is False


# ---------------------------------------------------------------------------
# deserialize
# ---------------------------------------------------------------------------


def test_deserialize_returns_none_for_none(serializer: ToolSerializer) -> None:
    assert serializer.deserialize(None) is None


def test_deserialize_returns_none_for_empty_dict(serializer: ToolSerializer) -> None:
    assert serializer.deserialize({}) is None


def test_deserialize_returns_tool_entity(serializer: ToolSerializer) -> None:
    data = {
        "title": "hammer",
        "description": "A tool.",
        "icon_path": "hammer.png",
        "is_enabled": True,
    }
    assert isinstance(serializer.deserialize(data), ToolEntity)


def test_deserialize_maps_fields(serializer: ToolSerializer) -> None:
    data = {
        "title": "hammer",
        "description": "A tool.",
        "icon_path": "hammer.png",
        "is_enabled": True,
    }
    entity = serializer.deserialize(data)
    assert entity.title == "hammer"
    assert entity.description == "A tool."
    assert entity.icon_path == "hammer.png"
    assert entity.is_enabled is True


def test_deserialize_coerces_is_enabled_to_bool(serializer: ToolSerializer) -> None:
    data = {"title": "x", "description": "d", "icon_path": "p", "is_enabled": 0}
    assert serializer.deserialize(data).is_enabled is False


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_round_trip_preserves_entity(serializer: ToolSerializer, tool_enabled: ToolEntity) -> None:
    assert serializer.deserialize(serializer.serialize(tool_enabled)) == tool_enabled


def test_round_trip_preserves_is_enabled_false(
    serializer: ToolSerializer, tool_disabled: ToolEntity
) -> None:
    assert serializer.deserialize(serializer.serialize(tool_disabled)).is_enabled is False

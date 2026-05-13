"""Unit tests for ToolSerializer (SQLite tuple-based)."""

import pytest

from domain.entities.tool import ToolEntity
from serializers.tool import ToolSerializer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def serializer() -> ToolSerializer:
    """Return a fresh ToolSerializer instance."""
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


def test_serialize_returns_tuple(
    serializer: ToolSerializer,
    tool_enabled: ToolEntity,
) -> None:
    result = serializer.serialize(tool_enabled)
    assert isinstance(result, tuple)


def test_serialize_tuple_has_four_elements(
    serializer: ToolSerializer,
    tool_enabled: ToolEntity,
) -> None:
    result = serializer.serialize(tool_enabled)
    assert len(result) == 4


def test_serialize_maps_title_to_first_position(
    serializer: ToolSerializer,
    tool_enabled: ToolEntity,
) -> None:
    result = serializer.serialize(tool_enabled)
    assert result[0] == tool_enabled.title


def test_serialize_maps_description_to_second_position(
    serializer: ToolSerializer,
    tool_enabled: ToolEntity,
) -> None:
    result = serializer.serialize(tool_enabled)
    assert result[1] == tool_enabled.description


def test_serialize_maps_icon_path_to_third_position(
    serializer: ToolSerializer,
    tool_enabled: ToolEntity,
) -> None:
    result = serializer.serialize(tool_enabled)
    assert result[2] == tool_enabled.icon_path


def test_serialize_maps_is_enabled_true_to_fourth_position(
    serializer: ToolSerializer,
    tool_enabled: ToolEntity,
) -> None:
    result = serializer.serialize(tool_enabled)
    assert result[3] is True


def test_serialize_maps_is_enabled_false_to_fourth_position(
    serializer: ToolSerializer,
    tool_disabled: ToolEntity,
) -> None:
    result = serializer.serialize(tool_disabled)
    assert result[3] is False


# ---------------------------------------------------------------------------
# deserialize
# ---------------------------------------------------------------------------


def test_deserialize_returns_none_for_none_row(serializer: ToolSerializer) -> None:
    assert serializer.deserialize(None) is None


def test_deserialize_returns_none_for_empty_tuple(serializer: ToolSerializer) -> None:
    assert serializer.deserialize(()) is None


def test_deserialize_returns_tool_entity(
    serializer: ToolSerializer,
    tool_enabled: ToolEntity,
) -> None:
    row = ("hammer", "A tool for driving nails into wood.", "hammer.png", 1)
    result = serializer.deserialize(row)
    assert isinstance(result, ToolEntity)


def test_deserialize_maps_title_correctly(serializer: ToolSerializer) -> None:
    row = ("hammer", "A tool.", "hammer.png", 1)
    assert serializer.deserialize(row).title == "hammer"


def test_deserialize_maps_description_correctly(serializer: ToolSerializer) -> None:
    row = ("hammer", "A tool.", "hammer.png", 1)
    assert serializer.deserialize(row).description == "A tool."


def test_deserialize_maps_icon_path_correctly(serializer: ToolSerializer) -> None:
    row = ("hammer", "A tool.", "hammer.png", 1)
    assert serializer.deserialize(row).icon_path == "hammer.png"


def test_deserialize_maps_is_enabled_1_to_true(serializer: ToolSerializer) -> None:
    row = ("hammer", "A tool.", "hammer.png", 1)
    assert serializer.deserialize(row).is_enabled is True


def test_deserialize_maps_is_enabled_0_to_false(serializer: ToolSerializer) -> None:
    row = ("screwdriver", "A tool.", "screwdriver.png", 0)
    assert serializer.deserialize(row).is_enabled is False


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_serialize_then_deserialize_returns_original_entity(
    serializer: ToolSerializer,
    tool_enabled: ToolEntity,
) -> None:
    row = serializer.serialize(tool_enabled)
    result = serializer.deserialize(row)
    assert result == tool_enabled


def test_round_trip_preserves_is_enabled_false(
    serializer: ToolSerializer,
    tool_disabled: ToolEntity,
) -> None:
    row = serializer.serialize(tool_disabled)
    result = serializer.deserialize(row)
    assert result.is_enabled is False

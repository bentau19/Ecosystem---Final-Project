from dataclasses import asdict

import pytest

from entities.tool import ToolEntity
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
        is_enabled=True,
        description="A tool for driving nails into wood.",
        icon_path="hammer.png",
    )


@pytest.fixture()
def tool_disabled() -> ToolEntity:
    return ToolEntity(
        title="screwdriver",
        is_enabled=False,
        description="A tool for driving screws into wood.",
        icon_path="screwdriver.png",
    )


@pytest.fixture()
def tool_another_enabled() -> ToolEntity:
    return ToolEntity(
        title="wrench",
        is_enabled=True,
        description="A tool for tightening or loosening nuts and bolts.",
        icon_path="wrench.png",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_serialize_empty_dict_returns_empty_dict(serializer: ToolSerializer):
    assert serializer.serialize({}) == {}


def test_serialize_single_entity_returns_correct_dict(
        serializer: ToolSerializer,
        tool_enabled: ToolEntity,
):
    result = serializer.serialize({tool_enabled.title: tool_enabled})
    assert result == {tool_enabled.title: asdict(tool_enabled)}


def test_serialize_multiple_entities_returns_correct_dict(
        serializer: ToolSerializer,
        tool_enabled: ToolEntity,
        tool_disabled: ToolEntity,
        tool_another_enabled: ToolEntity,
):
    data = {
        tool_enabled.title: tool_enabled,
        tool_disabled.title: tool_disabled,
        tool_another_enabled.title: tool_another_enabled,
    }
    result = serializer.serialize(data)
    assert result == {
        tool_enabled.title: asdict(tool_enabled),
        tool_disabled.title: asdict(tool_disabled),
        tool_another_enabled.title: asdict(tool_another_enabled),
    }


def test_serialize_preserves_string_keys(
        serializer: ToolSerializer,
        tool_enabled: ToolEntity,
):
    result = serializer.serialize({tool_enabled.title: tool_enabled})
    assert isinstance(list(result.keys())[0], str)


def test_deserialize_empty_dict_returns_empty_dict(serializer: ToolSerializer):
    assert serializer.deserialize({}) == {}


def test_deserialize_single_entry_returns_correct_tool_entity(
        serializer: ToolSerializer,
        tool_enabled: ToolEntity,
):
    data = {tool_enabled.title: asdict(tool_enabled)}
    result = serializer.deserialize(data)
    assert result == {tool_enabled.title: tool_enabled}
    assert isinstance(result[tool_enabled.title], ToolEntity)


def test_deserialize_multiple_entries_returns_correct_tool_entities(
        serializer: ToolSerializer,
        tool_enabled: ToolEntity,
        tool_disabled: ToolEntity,
        tool_another_enabled: ToolEntity,
):
    data = {
        tool_enabled.title: asdict(tool_enabled),
        tool_disabled.title: asdict(tool_disabled),
        tool_another_enabled.title: asdict(tool_another_enabled),
    }
    result = serializer.deserialize(data)
    assert result == {
        tool_enabled.title: tool_enabled,
        tool_disabled.title: tool_disabled,
        tool_another_enabled.title: tool_another_enabled,
    }


def test_serialize_then_deserialize_returns_original_data(
        serializer: ToolSerializer,
        tool_enabled: ToolEntity,
        tool_disabled: ToolEntity,
        tool_another_enabled: ToolEntity,
):
    original = {
        tool_enabled.title: tool_enabled,
        tool_disabled.title: tool_disabled,
        tool_another_enabled.title: tool_another_enabled,
    }
    assert serializer.deserialize(serializer.serialize(original)) == original

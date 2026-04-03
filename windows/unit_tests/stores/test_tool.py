import json
from unittest.mock import MagicMock

import pytest

from entities.tool import ToolEntity
from serializers.interfaces.base import ISerializer
from stores.tool import ToolStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_serializer() -> MagicMock:
    return MagicMock(spec=ISerializer)


@pytest.fixture()
def store(mock_serializer: MagicMock, tmp_path) -> ToolStore:
    return ToolStore(serializer=mock_serializer, json_path=str(tmp_path / "tool.json"))


@pytest.fixture()
def tool_enabled() -> ToolEntity:
    return ToolEntity(
        title="hammer",
        is_enabled=True,
        description="A tool for hammering nails.",
        icon_path="icon.png",
        icon_background_color="#FFFFFF"
    )


@pytest.fixture()
def tool_disabled() -> ToolEntity:
    return ToolEntity(
        title="screwdriver",
        is_enabled=False,
        description="A tool for driving screws.",
        icon_path="icon.png",
        icon_background_color="#FFFFFF"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_load_when_file_does_not_exist_returns_empty_dict(store: ToolStore):
    assert store.load() == {}


def test_load_when_file_exists_returns_deserialized_data(
        store: ToolStore,
        mock_serializer: MagicMock,
        tool_enabled: ToolEntity,
        tmp_path,
):
    raw = {"hammer": {"title": "hammer", "is_enabled": True}}
    json_file = tmp_path / "tool.json"
    json_file.write_text(json.dumps(raw))

    mock_serializer.deserialize.return_value = {"hammer": tool_enabled}

    result = store.load()

    mock_serializer.deserialize.assert_called_once_with(raw)
    assert result == {"hammer": tool_enabled}


def test_load_when_file_is_empty_json_returns_deserialized_empty(
        store: ToolStore,
        mock_serializer: MagicMock,
        tmp_path,
):
    json_file = tmp_path / "tool.json"
    json_file.write_text(json.dumps({}))

    mock_serializer.deserialize.return_value = {}

    result = store.load()

    mock_serializer.deserialize.assert_called_once_with({})
    assert result == {}


def test_save_serializes_data_and_writes_to_file(
        store: ToolStore,
        mock_serializer: MagicMock,
        tool_enabled: ToolEntity,
        tmp_path,
):
    data = {"hammer": tool_enabled}
    serialized = {"hammer": {"title": "hammer", "is_enabled": True}}
    mock_serializer.serialize.return_value = serialized

    store.save(data)
    mock_serializer.serialize.assert_called_once_with(data)
    json_file = tmp_path / "tool.json"
    assert json_file.exists()
    assert json.loads(json_file.read_text()) == serialized


def test_save_multiple_entities_writes_all_to_file(
        store: ToolStore,
        mock_serializer: MagicMock,
        tool_enabled: ToolEntity,
        tool_disabled: ToolEntity,
        tmp_path,
):
    data = {
        tool_enabled.title: tool_enabled,
        tool_disabled.title: tool_disabled,
    }
    serialized = {
        "hammer": {"title": "hammer", "is_enabled": True},
        "screwdriver": {"title": "screwdriver", "is_enabled": False},
    }
    mock_serializer.serialize.return_value = serialized

    store.save(data)

    json_file = tmp_path / "tool.json"
    assert json.loads(json_file.read_text()) == serialized


def test_save_preserves_is_enabled_false_in_file(
        store: ToolStore,
        mock_serializer: MagicMock,
        tool_disabled: ToolEntity,
        tmp_path,
):
    data = {tool_disabled.title: tool_disabled}
    serialized = {"screwdriver": {"title": "screwdriver", "is_enabled": False}}
    mock_serializer.serialize.return_value = serialized

    store.save(data)

    json_file = tmp_path / "tool.json"
    written = json.loads(json_file.read_text())
    assert written["screwdriver"]["is_enabled"] is False


# --- round trip ---


def test_save_then_load_returns_original_data(
        tool_enabled: ToolEntity,
        tool_disabled: ToolEntity,
        tmp_path,
):
    from serializers.tool import ToolSerializer

    real_serializer = ToolSerializer()
    store = ToolStore(serializer=real_serializer, json_path=str(tmp_path / "tool.json"))

    original = {
        tool_enabled.title: tool_enabled,
        tool_disabled.title: tool_disabled,
    }

    store.save(original)
    result = store.load()

    assert result == original

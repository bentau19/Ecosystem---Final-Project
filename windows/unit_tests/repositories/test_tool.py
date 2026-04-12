from unittest.mock import MagicMock

import pytest

from entities.tool import ToolEntity
from repositories.tool import ToolRepository
from stores.interfaces.base import IStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset the ToolRepository singleton before and after every test.

    Without this, the first test's instance leaks into every subsequent
    test — __init__ is guarded by _initialized so new mock stores would
    never be injected.
    """
    ToolRepository._instance = None
    ToolRepository._initialized = False
    yield
    ToolRepository._instance = None
    ToolRepository._initialized = False

@pytest.fixture()
def tool_enabled() -> ToolEntity:
    return ToolEntity(
        title="hammer",
        description="A tool for hammering",
        icon_path="hammer.png",
        icon_background_color="#FFFFFF",
        is_enabled=True,
    )


@pytest.fixture()
def tool_disabled() -> ToolEntity:
    return ToolEntity(
        title="screwdriver",
        is_enabled=False,
        description="A tool for screwdriving",
        icon_path="screwdriver.png",
        icon_background_color="#FFFFFF",
    )


@pytest.fixture()
def tool_another_enabled() -> ToolEntity:
    return ToolEntity(
        title="wrench",
        is_enabled=True,
        description="A tool for wrenching",
        icon_path="wrench.png",
        icon_background_color="#FFFFFF",
    )


@pytest.fixture()
def mock_store_empty() -> MagicMock:
    store: MagicMock = MagicMock(spec=IStore)
    store.load.return_value = {}
    return store


@pytest.fixture()
def mock_store_with_items(
        tool_enabled: ToolEntity,
        tool_disabled: ToolEntity,
        tool_another_enabled: ToolEntity,
) -> MagicMock:
    store: MagicMock = MagicMock(spec=IStore)
    store.load.return_value = {
        tool_enabled.title: tool_enabled,
        tool_disabled.title: tool_disabled,
        tool_another_enabled.title: tool_another_enabled,
    }
    return store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# --- load ---
def test_load_when_store_is_empty_returns_empty_dict(mock_store_empty: MagicMock):
    repo = ToolRepository(store=mock_store_empty)
    assert repo.load() == {}


def test_load_when_store_has_items_returns_all_tools(mock_store_with_items: MagicMock):
    repo = ToolRepository(store=mock_store_with_items)
    assert repo.load() == mock_store_with_items.load.return_value


# --- get_by_id ---

def test_get_by_id_when_tool_exists_returns_correct_tool(
        mock_store_with_items: MagicMock,
        tool_enabled: ToolEntity,
        tool_disabled: ToolEntity,
):
    repo = ToolRepository(store=mock_store_with_items)
    assert repo.get_by_id(tool_enabled.title) == tool_enabled
    assert repo.get_by_id(tool_disabled.title) == tool_disabled


def test_get_by_id_when_tool_does_not_exist_returns_none(mock_store_empty: MagicMock):
    repo = ToolRepository(store=mock_store_empty)
    assert repo.get_by_id("nonexistent") is None


# --- get_all ---

def test_get_all_when_store_is_empty_returns_empty_list(mock_store_empty: MagicMock):
    repo = ToolRepository(store=mock_store_empty)
    assert repo.get_all() == []


def test_get_all_when_store_has_items_returns_all_tools(
        mock_store_with_items: MagicMock,
        tool_enabled: ToolEntity,
        tool_disabled: ToolEntity,
        tool_another_enabled: ToolEntity,
):
    repo = ToolRepository(store=mock_store_with_items)
    assert repo.get_all() == [tool_enabled, tool_disabled, tool_another_enabled]


# --- get_all_enabled ---

def test_get_all_enabled_returns_only_enabled_tools(
        mock_store_with_items: MagicMock,
        tool_enabled: ToolEntity,
        tool_another_enabled: ToolEntity,
):
    repo = ToolRepository(store=mock_store_with_items)
    assert repo.get_all_enabled() == [tool_enabled, tool_another_enabled]


def test_get_all_enabled_when_no_enabled_tools_returns_empty_list(
        mock_store_empty: MagicMock,
        tool_disabled: ToolEntity,
):
    mock_store_empty.load.return_value = {tool_disabled.title: tool_disabled}
    repo = ToolRepository(store=mock_store_empty)
    assert repo.get_all_enabled() == []


# --- save ---

def test_save_new_tool_makes_it_retrievable_by_id(
        mock_store_empty: MagicMock,
        tool_enabled: ToolEntity,
):
    repo = ToolRepository(store=mock_store_empty)
    repo.save(tool_enabled)
    assert repo.get_by_id(tool_enabled.title) == tool_enabled


def test_save_new_tool_persists_to_store(
        mock_store_empty: MagicMock,
        tool_enabled: ToolEntity,
):
    repo = ToolRepository(store=mock_store_empty)
    repo.save(tool_enabled)
    mock_store_empty.save.assert_called_once()


def test_save_new_tool_emits_tool_saved_signal(
        mock_store_empty: MagicMock,
        tool_enabled: ToolEntity,
):
    repo = ToolRepository(store=mock_store_empty)
    received = []
    repo.tool_saved.connect(lambda t: received.append(t))
    repo.save(tool_enabled)
    assert received == [tool_enabled]


def test_save_duplicate_tool_raises_value_error(
        mock_store_empty: MagicMock,
        tool_enabled: ToolEntity,
):
    repo = ToolRepository(store=mock_store_empty)
    repo.save(tool_enabled)
    with pytest.raises(ValueError, match=f"Tool with title '{tool_enabled.title}' already exists."):
        repo.save(tool_enabled)


# --- delete ---

def test_delete_existing_tool_returns_none_on_get(
        mock_store_with_items: MagicMock,
        tool_enabled: ToolEntity,
):
    repo = ToolRepository(store=mock_store_with_items)
    repo.delete(tool_enabled.title)
    assert repo.get_by_id(tool_enabled.title) is None


def test_delete_all_tools_results_in_empty_repo(
        mock_store_with_items: MagicMock,
        tool_enabled: ToolEntity,
        tool_disabled: ToolEntity,
        tool_another_enabled: ToolEntity,
):
    repo = ToolRepository(store=mock_store_with_items)
    repo.delete(tool_enabled.title)
    repo.delete(tool_disabled.title)
    repo.delete(tool_another_enabled.title)
    assert repo.get_all() == []


def test_delete_existing_tool_emits_tool_deleted_signal(
        mock_store_with_items: MagicMock,
        tool_enabled: ToolEntity,
):
    repo = ToolRepository(store=mock_store_with_items)
    received = []
    repo.tool_deleted.connect(lambda t: received.append(t))
    repo.delete(tool_enabled.title)
    assert received == [tool_enabled.title]


def test_delete_nonexistent_tool_still_emits_tool_deleted_signal(
        mock_store_empty: MagicMock,
):
    repo = ToolRepository(store=mock_store_empty)
    received = []
    repo.tool_deleted.connect(lambda t: received.append(t))
    repo.delete("nonexistent")
    assert received == ["nonexistent"]

"""Unit tests for ToolViewModel."""

from unittest.mock import MagicMock

import pytest

from domain.dto.tool import ToolDTO
from domain.entities.tool import ToolEntity
from viewmodels.tool import ToolViewModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tool_enabled() -> ToolEntity:
    return ToolEntity(
        title="hammer",
        description="A hammer",
        icon_path="icons/hammer.png",
        is_enabled=True,
    )


@pytest.fixture()
def tool_disabled() -> ToolEntity:
    return ToolEntity(
        title="screwdriver",
        description="A screwdriver",
        icon_path="icons/screwdriver.png",
        is_enabled=False,
    )


@pytest.fixture()
def tool_another_enabled() -> ToolEntity:
    return ToolEntity(
        title="wrench",
        description="A wrench",
        icon_path="icons/wrench.png",
        is_enabled=True,
    )


@pytest.fixture()
def mock_service() -> MagicMock:
    """Mock ToolService with wired signal stubs."""
    service = MagicMock()
    service.all_enabled_tools_fetched = MagicMock()
    service.all_enabled_tools_fetched.connect = MagicMock()
    return service


@pytest.fixture()
def view_model(mock_service: MagicMock) -> ToolViewModel:
    return ToolViewModel(tool_service=mock_service)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_convert_to_dto_returns_tool_dto(tool_enabled: ToolEntity):
    result = ToolViewModel._convert_to_dto(tool_enabled)
    assert isinstance(result, ToolDTO)


def test_convert_to_dto_maps_all_fields_correctly(tool_enabled: ToolEntity):
    result = ToolViewModel._convert_to_dto(tool_enabled)
    assert result.title == tool_enabled.title
    assert result.description == tool_enabled.description
    assert result.icon_path == tool_enabled.icon_path
    assert result.is_enabled == tool_enabled.is_enabled


def test_convert_to_dto_preserves_is_enabled_false(tool_disabled: ToolEntity):
    result = ToolViewModel._convert_to_dto(tool_disabled)
    assert result.is_enabled is False


def test_init_enabled_tools_starts_empty(mock_service: MagicMock) -> None:
    vm = ToolViewModel(tool_service=mock_service)
    assert vm._enabled_tools == []


def test_init_calls_start_and_fetch_all_enabled(mock_service: MagicMock) -> None:
    ToolViewModel(tool_service=mock_service)
    mock_service.start.assert_called_once()
    mock_service.fetch_all_enabled.assert_called_once()


def test_init_connects_to_all_enabled_tools_fetched(mock_service: MagicMock) -> None:
    ToolViewModel(tool_service=mock_service)
    mock_service.all_enabled_tools_fetched.connect.assert_called_once()


def test_on_all_enabled_fetched_populates_enabled_tools(
        view_model: ToolViewModel,
        tool_enabled: ToolEntity,
        tool_another_enabled: ToolEntity,
) -> None:
    view_model._on_all_enabled_fetched([tool_enabled, tool_another_enabled])
    assert len(view_model._enabled_tools) == 2


def test_on_all_enabled_fetched_emits_tools_loaded(
        view_model: ToolViewModel,
        tool_enabled: ToolEntity,
) -> None:
    received: list = []
    view_model.tools_loaded.connect(lambda tools: received.append(tools))

    view_model._on_all_enabled_fetched([tool_enabled])

    assert len(received) == 1
    assert received[0][0].title == tool_enabled.title


def test_on_all_enabled_fetched_emits_tools_changed(
        view_model: ToolViewModel,
        tool_enabled: ToolEntity,
) -> None:
    received: list = []
    view_model.tools_changed.connect(lambda tools: received.append(tools))

    view_model._on_all_enabled_fetched([tool_enabled])

    assert len(received) == 1


def test_on_all_enabled_fetched_with_empty_list_clears_tools(
        view_model: ToolViewModel,
        tool_enabled: ToolEntity,
) -> None:
    view_model._on_all_enabled_fetched([tool_enabled])
    view_model._on_all_enabled_fetched([])
    assert view_model._enabled_tools == []


def test_load_enabled_tools_emits_tools_loaded_signal(view_model: ToolViewModel) -> None:
    received = []
    view_model.tools_loaded.connect(lambda tools: received.append(tools))

    view_model.load_enabled_tools()

    assert len(received) == 1


def test_load_enabled_tools_emits_correct_tools(
        view_model: ToolViewModel,
        tool_enabled: ToolEntity,
) -> None:
    view_model._on_all_enabled_fetched([tool_enabled])

    received = []
    view_model.tools_loaded.connect(lambda tools: received.append(tools))
    view_model.load_enabled_tools()

    assert len(received[0]) == 1
    assert received[0][0].title == tool_enabled.title


def test_load_enabled_tools_when_no_enabled_tools_emits_empty_list(
        view_model: ToolViewModel,
) -> None:
    received = []
    view_model.tools_loaded.connect(lambda tools: received.append(tools))
    view_model.load_enabled_tools()

    assert received == [[]]

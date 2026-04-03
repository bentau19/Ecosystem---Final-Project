from unittest.mock import MagicMock, patch

import pytest

from dto.tool import ToolDTO
from entities.tool import ToolEntity
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
        icon_background_color="#FF0000",
        is_enabled=True,
    )


@pytest.fixture()
def tool_disabled() -> ToolEntity:
    return ToolEntity(
        title="screwdriver",
        description="A screwdriver",
        icon_path="icons/screwdriver.png",
        icon_background_color="#00FF00",
        is_enabled=False,
    )


@pytest.fixture()
def tool_another_enabled() -> ToolEntity:
    return ToolEntity(
        title="wrench",
        description="A wrench",
        icon_path="icons/wrench.png",
        icon_background_color="#0000FF",
        is_enabled=True,
    )


@pytest.fixture()
def mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.tool_saved = MagicMock()
    repo.tool_saved.connect = MagicMock()
    repo.tool_deleted = MagicMock()
    repo.tool_deleted.connect = MagicMock()
    repo.get_all_enabled.return_value = []
    return repo


@pytest.fixture()
def view_model(mock_repo: MagicMock) -> ToolViewModel:
    with patch("viewmodels.tool.app_state") as mock_app_state:
        mock_app_state.tools_repository = mock_repo
        vm = ToolViewModel()
    return vm


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
    assert result.icon_background_color == tool_enabled.icon_background_color
    assert result.is_enabled == tool_enabled.is_enabled


def test_convert_to_dto_preserves_is_enabled_false(tool_disabled: ToolEntity):
    result = ToolViewModel._convert_to_dto(tool_disabled)
    assert result.is_enabled is False


def test_init_loads_enabled_tools_from_repo(
        mock_repo: MagicMock,
        tool_enabled: ToolEntity,
        tool_another_enabled: ToolEntity,
):
    mock_repo.get_all_enabled.return_value = [tool_enabled, tool_another_enabled]
    with patch("viewmodels.tool.app_state") as mock_app_state:
        mock_app_state.tools_repository = mock_repo
        vm = ToolViewModel()

    assert len(vm._enabled_tools) == 2


def test_init_connects_to_repo_signals(mock_repo: MagicMock):
    with patch("viewmodels.tool.app_state") as mock_app_state:
        mock_app_state.tools_repository = mock_repo
        ToolViewModel()

    mock_repo.tool_saved.connect.assert_called_once()
    mock_repo.tool_deleted.connect.assert_called_once()


def test_load_enabled_tools_emits_tools_loaded_signal(
        view_model: ToolViewModel,
):
    received = []
    view_model.tools_loaded.connect(lambda tools: received.append(tools))

    view_model.load_enabled_tools()

    assert len(received) == 1


def test_load_enabled_tools_emits_correct_tools(
        mock_repo: MagicMock,
        tool_enabled: ToolEntity,
):
    mock_repo.get_all_enabled.return_value = [tool_enabled]
    with patch("viewmodels.tool.app_state") as mock_app_state:
        mock_app_state.tools_repository = mock_repo
        vm = ToolViewModel()

    received = []
    vm.tools_loaded.connect(lambda tools: received.append(tools))
    vm.load_enabled_tools()

    assert len(received[0]) == 1
    assert received[0][0].title == tool_enabled.title


def test_load_enabled_tools_emits_tool_count_changed_signal(
        mock_repo: MagicMock,
        tool_enabled: ToolEntity,
        tool_another_enabled: ToolEntity,
):
    mock_repo.get_all_enabled.return_value = [tool_enabled, tool_another_enabled]
    with patch("viewmodels.tool.app_state") as mock_app_state:
        mock_app_state.tools_repository = mock_repo
        vm = ToolViewModel()

    received = []
    vm.tool_count_changed.connect(lambda count: received.append(count))
    vm.load_enabled_tools()

    assert received == [2]


def test_load_enabled_tools_when_no_enabled_tools_emits_empty_list(
        view_model: ToolViewModel,
):
    received = []
    view_model.tools_loaded.connect(lambda tools: received.append(tools))
    view_model.load_enabled_tools()

    assert received == [[]]


def test_on_tool_added_emits_tool_added_signal(
        view_model: ToolViewModel,
        tool_enabled: ToolEntity,
):
    received = []
    view_model.tool_added.connect(lambda dto: received.append(dto))

    view_model._on_tool_added(tool_enabled)

    assert len(received) == 1
    assert isinstance(received[0], ToolDTO)


def test_on_tool_added_appends_tool_to_enabled_tools(
        view_model: ToolViewModel,
        tool_enabled: ToolEntity,
):
    view_model._on_tool_added(tool_enabled)
    assert len(view_model._enabled_tools) == 1
    assert view_model._enabled_tools[0].title == tool_enabled.title


def test_on_tool_added_emits_tool_count_changed_signal(
        view_model: ToolViewModel,
        mock_repo: MagicMock,
        tool_enabled: ToolEntity,
        tool_another_enabled: ToolEntity,
):
    received = []
    view_model.tool_count_changed.connect(lambda count: received.append(count))

    view_model._on_tool_added(tool_enabled)

    assert received == [1]

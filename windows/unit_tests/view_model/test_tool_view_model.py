import pytest
from unittest.mock import MagicMock, patch

from dto.tool import ToolDTO
from entities.tool import ToolEntity


def _make_tool_entity(title="Hammer", enabled=True):
    e = MagicMock(spec=ToolEntity)
    e.title = title
    e.description = f"{title} description"
    e.icon_path = f"icons/{title.lower()}.png"
    e.icon_background_color = "#AABBCC"
    e.is_enabled = enabled
    return e


def _make_tool_dto(title="Hammer", enabled=True):
    return ToolDTO(
        title=title,
        description=f"{title} description",
        icon_path=f"icons/{title.lower()}.png",
        icon_background_color="#AABBCC",
        is_enabled=enabled,
    )


@pytest.fixture()
def mock_repo():
    repo = MagicMock()
    repo.tool_saved = MagicMock()
    repo.tool_deleted = MagicMock()
    repo.get_all_enabled.return_value = []
    return repo


@pytest.fixture()
def view_model(mock_repo, qapp):
    with patch("view_model.tool.app_state") as mock_app_state:
        mock_app_state.tools_repository = mock_repo
        from view_model.tool import ToolViewModel
        vm = ToolViewModel()
    return vm, mock_repo


class TestConvertToDto:
    def setup_method(self):
        with patch("view_model.tool.app_state") as m:
            m.tools_repository = MagicMock(
                tool_saved=MagicMock(),
                tool_deleted=MagicMock(),
                get_all_enabled=MagicMock(return_value=[]),
            )
            from view_model.tool import ToolViewModel
            self.ToolViewModel = ToolViewModel

    def test_converts_entity_to_dto(self):
        entity = _make_tool_entity("Wrench", enabled=False)
        dto = self.ToolViewModel._convert_to_dto(entity)
        assert isinstance(dto, ToolDTO)
        assert dto.title == "Wrench"
        assert dto.is_enabled is False

    def test_dto_fields_match_entity(self):
        entity = _make_tool_entity("Drill")
        dto = self.ToolViewModel._convert_to_dto(entity)
        assert dto.description == entity.description
        assert dto.icon_path == entity.icon_path
        assert dto.icon_background_color == entity.icon_background_color


class TestInit:
    def test_preloads_enabled_tools(self, qapp):
        enabled = [_make_tool_entity("Saw"), _make_tool_entity("Drill")]
        mock_repo = MagicMock(
            tool_saved=MagicMock(),
            tool_deleted=MagicMock(),
            get_all_enabled=MagicMock(return_value=enabled),
        )
        with patch("view_model.tool.app_state") as m:
            m.tools_repository = mock_repo
            from view_model.tool import ToolViewModel
            vm = ToolViewModel()

        assert len(vm._enabled_tools) == 2
        assert all(isinstance(t, ToolDTO) for t in vm._enabled_tools)


class TestLoadEnabledTools:
    def test_emits_tools_loaded_and_count(self, view_model):
        vm, repo = view_model
        tool = _make_tool_entity("Hammer")
        repo.get_all_enabled.return_value = [tool]
        vm._enabled_tools = [vm._convert_to_dto(tool)]

        loaded = []
        counts = []
        vm.tools_loaded.connect(loaded.append)
        vm.tool_count_changed.connect(counts.append)
        vm.load_enabled_tools()

        assert len(loaded) == 1
        assert len(loaded[0]) == 1
        assert counts[-1] == 1

    def test_emits_empty_list_when_no_tools(self, view_model):
        vm, _ = view_model
        vm._enabled_tools = []

        loaded = []
        vm.tools_loaded.connect(loaded.append)
        vm.load_enabled_tools()

        assert loaded == [[]]


class TestOnToolAdded:
    def test_emits_tool_added_with_dto(self, view_model):
        vm, _ = view_model
        entity = _make_tool_entity("Screwdriver")

        received = []
        vm.tool_added.connect(received.append)
        vm._on_tool_added(entity)

        assert len(received) == 1
        assert isinstance(received[0], ToolDTO)
        assert received[0].title == "Screwdriver"

    def test_appends_to_enabled_tools(self, view_model):
        vm, _ = view_model
        vm._enabled_tools = []
        entity = _make_tool_entity("Chisel")

        vm._on_tool_added(entity)

        assert len(vm._enabled_tools) == 1

    def test_emits_tool_count_changed(self, view_model):
        vm, _ = view_model
        vm._enabled_tools = []
        entity = _make_tool_entity("Pliers")

        counts = []
        vm.tool_count_changed.connect(counts.append)
        vm._on_tool_added(entity)

        assert counts[-1] == 1


class TestOnToolDeleted:
    def test_emits_tool_deleted_with_id(self, view_model):
        vm, repo = view_model
        repo.get_all_enabled.return_value = []

        received = []
        vm.tool_deleted.connect(received.append)
        vm._on_tool_deleted("Hammer")

        assert "Hammer" in received

    def test_refreshes_enabled_tools_from_repo(self, view_model):
        vm, repo = view_model
        remaining = [_make_tool_entity("Saw")]
        repo.get_all_enabled.return_value = remaining

        vm._on_tool_deleted("Hammer")

        assert len(vm._enabled_tools) == 1

    def test_emits_count_after_deletion(self, view_model):
        vm, repo = view_model
        repo.get_all_enabled.return_value = []

        counts = []
        vm.tool_count_changed.connect(counts.append)
        vm._on_tool_deleted("Hammer")

        assert counts[-1] == 0


class TestOnToolUpdated:
    def test_emits_tool_updated_with_title(self, view_model):
        vm, repo = view_model
        entity = _make_tool_entity("Wrench")
        repo.get_all_enabled.return_value = [entity]

        received = []
        vm.tool_updated.connect(received.append)
        vm._on_tool_updated(entity)

        assert received == ["Wrench"]

    def test_refreshes_enabled_tools(self, view_model):
        vm, repo = view_model
        entity = _make_tool_entity("Wrench")
        repo.get_all_enabled.return_value = [entity]

        vm._on_tool_updated(entity)

        assert len(vm._enabled_tools) == 1
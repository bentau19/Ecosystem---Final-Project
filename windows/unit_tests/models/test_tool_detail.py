from unittest.mock import MagicMock

from data_classes.tool_detail import ToolDetail
from models.tool_detail import ToolDetailModel
from repositories.tool_detail import ToolDetailRepository


class TestToolDetailModel:
    def setup_method(self):
        self.repo = ToolDetailRepository()
        self.model = ToolDetailModel(self.repo)

    def test_only_enabled_returned(self):
        assert all(t.is_enabled for t in self.model.get_active_tools())

    def test_no_disabled_returned(self):
        assert not any(not t.is_enabled for t in self.model.get_active_tools())

    def test_correct_count(self):
        assert len(self.model.get_active_tools()) == 6

    def test_change_status_disables(self):
        self.model.change_active_status("Tool 1", is_enabled=False)
        assert self.repo.get_tool("Tool 1").is_enabled is False

    def test_change_status_enables(self):
        self.model.change_active_status("Tool 3", is_enabled=True)
        assert self.repo.get_tool("Tool 3").is_enabled is True

    def test_count_decreases_after_disable(self):
        before = len(self.model.get_active_tools())
        self.model.change_active_status("Tool 1", is_enabled=False)
        assert len(self.model.get_active_tools()) == before - 1

    def test_count_increases_after_enable(self):
        before = len(self.model.get_active_tools())
        self.model.change_active_status("Tool 3", is_enabled=True)
        assert len(self.model.get_active_tools()) == before + 1

    def test_uses_injected_repo(self):
        mock_repo = MagicMock()
        mock_repo.fetch_tools.return_value = [
            ToolDetail("A", "d", "i.png", "#FFF", True),
            ToolDetail("B", "d", "i.png", "#FFF", False),
        ]
        result = ToolDetailModel(mock_repo).get_active_tools()
        assert len(result) == 1 and result[0].title == "A"

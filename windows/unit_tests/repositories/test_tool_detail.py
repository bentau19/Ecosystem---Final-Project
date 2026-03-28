from typing import cast

import pytest

from data_classes.tool_detail import ToolDetail
from repositories.tool_detail import ToolDetailRepository


class TestToolDetailRepository:
    def setup_method(self):
        self.repo = ToolDetailRepository()

    def test_fetch_returns_list(self):
        assert isinstance(self.repo.fetch_tools(), list)

    def test_fetch_returns_ten(self):
        assert len(self.repo.fetch_tools()) == 10

    def test_fetch_all_tool_detail_instances(self):
        assert all(isinstance(t, ToolDetail) for t in self.repo.fetch_tools())

    def test_six_enabled(self):
        assert len([t for t in self.repo.fetch_tools() if t.is_enabled]) == 6

    def test_four_disabled(self):
        assert len([t for t in self.repo.fetch_tools() if not t.is_enabled]) == 4

    def test_get_tool_correct(self):
        assert self.repo.get_tool("Tool 1").title == "Tool 1"

    def test_get_tool_invalid_raises(self):
        with pytest.raises(ValueError):
            self.repo.get_tool("Ghost")

    def test_update_description(self):
        self.repo.update_tool("Tool 1", description="New")
        assert self.repo.get_tool("Tool 1").description == "New"

    def test_update_disable(self):
        self.repo.update_tool("Tool 1", is_enabled=False)
        assert self.repo.get_tool("Tool 1").is_enabled is False

    def test_update_enable(self):
        self.repo.update_tool("Tool 3", is_enabled=True)
        assert self.repo.get_tool("Tool 3").is_enabled is True

    def test_update_icon(self):
        self.repo.update_tool("Tool 2", icon="new.png")
        assert self.repo.get_tool("Tool 2").icon_path == "new.png"

    def test_update_background_color(self):
        self.repo.update_tool("Tool 2", background_color="#123456")
        assert self.repo.get_tool("Tool 2").icon_background_color == "#123456"

    def test_update_none_ignored(self):
        self.repo.update_tool("Tool 1", description=None)
        assert self.repo.get_tool("Tool 1").description == "Description 1"

    def test_update_nonexistent_raises(self):
        with pytest.raises(cast(tuple[type[BaseException], ...], (ValueError, KeyError))):
            self.repo.update_tool("Ghost", is_enabled=True)

    def test_update_does_not_affect_others(self):
        self.repo.update_tool("Tool 1", description="Changed")
        assert self.repo.get_tool("Tool 2").description == "Description 2"

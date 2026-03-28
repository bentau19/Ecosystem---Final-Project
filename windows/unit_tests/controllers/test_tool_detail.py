from unittest.mock import MagicMock

from controller.tool_detail import ToolDetailController
from data_classes.tool_detail import ToolDetail


class TestToolDetailController:
    def test_load_active_tools(self):
        model_mock = MagicMock()
        view_mock = MagicMock()
        model_mock.get_active_tools.return_value = [
            ToolDetail("Title 1", "description 1", "image 1", "#FF0000", True),
            ToolDetail("Title 2", "description 2", "image 2", "#00FF00", True),
        ]
        controller = ToolDetailController(view=view_mock, model=model_mock)
        controller.load_active_tools()
        model_mock.get_active_tools.assert_called_once()
        view_mock.update_tools_list.assert_called_once()

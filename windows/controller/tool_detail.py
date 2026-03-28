from typing import TYPE_CHECKING
from models.tool_detail import ToolDetailModel
from utils.app_state import app_state

if TYPE_CHECKING:
    from views.widgets.dashboard.tools_grid import ToolsGrid


class ToolDetailController:
    def __init__(self, view: ToolsGrid, model: ToolDetailModel):
        self.model = model
        self.view: ToolsGrid = view

    def load_active_tools(self) -> None:
        tools = self.model.get_active_tools()
        self.view.update_tools_list(tools)

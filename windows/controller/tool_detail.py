from typing import List, TYPE_CHECKING

from data_classes.tool_detail import ToolDetail

if TYPE_CHECKING:
    from models.tool_detail import ToolDetailModel
    from views.widgets.dashboard.tools_grid import ToolsGrid


class ToolDetailController:
    """
    Controller class for ToolDetailModel and ToolsGrid.

    Attributes:
        model (ToolDetailModel): The model for tool details.
        view (ToolsGrid): The view for displaying the tools grid.
    """

    def __init__(self, view: ToolsGrid, model: ToolDetailModel):
        """
        Initialize the ToolDetailController.

        Args:
            view (ToolsGrid): The view for displaying the tools grid.
            model (ToolDetailModel): The model for tool details.
        """
        self.model: ToolDetailModel = model
        self.view: ToolsGrid = view

    def load_active_tools(self) -> None:
        """
        Load the active tools from the model and update the view.

        Returns:
            None
        """
        tools: List[ToolDetail] = self.model.get_active_tools()
        self.view.update_tools_list(tools)

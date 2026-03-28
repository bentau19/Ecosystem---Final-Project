from typing import List

from PySide6.QtCore import QObject, Signal

from data_classes.tool_detail import ToolDetail
from repositories.tool_detail import ToolDetailRepository


class ToolDetailModel(QObject):
    """
    Model class for the _tools' information.
    """

    def __init__(self, tools_repo: ToolDetailRepository, parent: QObject = None) -> None:
        """
        Initialize the ToolDetailModel.

        Args:
            tools_repo (ToolDetailRepository): The repository for _tools.
            parent (QObject, optional): The parent QObject. Defaults to None.
        """
        super().__init__(parent)

        self.tool_repo: ToolDetailRepository = tools_repo

    def get_active_tools(self) -> List[ToolDetail]:
        """
        Get the list of active _tools.

        Returns:
            List[ToolDetail]: The list of active _tools.
        """
        tools = self.tool_repo.fetch_tools()
        return [tool for tool in tools if tool.is_enabled]

    def change_active_status(self, title: str, is_enabled: bool) -> None:
        """
        Change the active status of a _tool.

        Args:
            title (str): The title of the _tool.
            is_enabled (bool): The new active status.

        Raises:
            ValueError: If the _tool does not exist.
        """
        self.tool_repo.update_tool(title, is_enabled=is_enabled)
from typing import List

from PySide6.QtCore import QObject, Signal

from data_classes.tool_detail import ToolDetail
from repositories.tool_detail import ToolDetailRepository


class ToolDetailModel(QObject):
    """
    Model class for the _tools' information.
    """

    tool_updated_signal = Signal(str)
    tool_added_signal = Signal(str)
    tool_removed_signal = Signal(str)

    def __init__(self, tools_repo: ToolDetailRepository, parent=None):
        super().__init__(parent)

        self.tool_repo: ToolDetailRepository = tools_repo

    def get_active_tools(self) -> List[ToolDetail]:
        tools = self.tool_repo.fetch_tools()
        return [tool for tool in tools if tool.is_enabled]

    def change_active_status(self, title: str, is_enabled: bool):
        self.tool_repo.update_tool(title, is_enabled=is_enabled)

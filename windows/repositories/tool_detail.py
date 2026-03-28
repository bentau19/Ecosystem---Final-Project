from typing import Dict, List, Optional

from data_classes.tool_detail import ToolDetail
from resources.paths import Icons


class ToolDetailRepository:
    """
    Repository for storing and retrieving _tools' details.
    """

    def __init__(self) -> None:
        """
        Initialize the repository with a set of _tools.
        """
        self._tools: Dict[str, ToolDetail] = {
            "Tool 1": ToolDetail("Tool 1", "Description 1", Icons.ANDROID, "#FFFFFF", True),
            "Tool 2": ToolDetail("Tool 2", "Description 2", Icons.ANDROID, "#FFFFFF", True),
            "Tool 3": ToolDetail("Tool 3", "Description 3", Icons.ANDROID, "#FFFFFF", False),
            "Tool 4": ToolDetail("Tool 4", "Description 4", Icons.ANDROID, "#FFFFFF", True),
            "Tool 5": ToolDetail("Tool 5", "Description 5", Icons.ANDROID, "#FFFFFF", False),
            "Tool 6": ToolDetail("Tool 6", "Description 6", Icons.ANDROID, "#FFFFFF", True),
            "Tool 7": ToolDetail("Tool 7", "Description 7", Icons.ANDROID, "#FFFFFF", False),
            "Tool 8": ToolDetail("Tool 8", "Description 8", Icons.ANDROID, "#FFFFFF", True),
            "Tool 9": ToolDetail("Tool 9", "Description 9", Icons.ANDROID, "#FFFFFF", False),
            "Tool 10": ToolDetail("Tool 10", "Description 10", Icons.ANDROID, "#FFFFFF", True),
        }

    def fetch_tools(self) -> List[ToolDetail]:
        """
        Retrieve all _tools from the repository.

        Returns:
            List[ToolDetail]: A list of _tools.
        """
        return list(self._tools.values())

    def update_tool(self, title: str, description: Optional[str] = None, icon: Optional[str] = None,
                    background_color: Optional[str] = None, is_enabled: Optional[bool] = None) -> None:
        """
        Update a tool's details.

        Args:
            title (str): The title of the _tool.
            description (Optional[str]): The updated description. Defaults to None.
            icon (Optional[str]): The updated icon path. Defaults to None.
            background_color (Optional[str]): The updated icon background color. Defaults to None.
            is_enabled (Optional[bool]): The updated enabled status. Defaults to None.

        Raises:
            ValueError: If the _tool with the given title does not exist.
        """
        if title not in self._tools:
            raise ValueError(f"Tool with title '{title}' does not exist.")

        tool = self._tools[title]

        if description is not None:
            tool.description = description

        if icon is not None:
            tool.icon_path = icon

        if background_color is not None:
            tool.icon_background_color = background_color

        if is_enabled is not None:
            tool.is_enabled = is_enabled

    def get_tool(self, title: str) -> ToolDetail:
        """
        Retrieve a tool based on its title.

        Args:
            title (str): The title of the _tool.

        Returns:
            ToolDetail: The _tool with the given title.

        Raises:
            ValueError: If the _tool with the given title does not exist.
        """
        if title not in self._tools:
            raise ValueError(f"Tool with title '{title}' does not exist.")
        return self._tools[title]
from dataclasses import dataclass


@dataclass
class ToolEntity:
    """
       tool entity.

       Attributes:
           title (str): The title of the tool.
           description (str): The description of the tool.
           icon_path (str): The path to the tool icon.
           icon_background_color (str): The background color of the tool icon.
           is_enabled (bool): Indicates whether the tool is enabled.
       """
    title: str
    description: str
    icon_path: str
    icon_background_color: str
    is_enabled: bool

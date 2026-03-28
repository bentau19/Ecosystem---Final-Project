from dataclasses import dataclass


@dataclass
class ToolDetail:
    title: str
    description: str
    icon_path: str
    icon_background_color: str
    is_enabled: bool

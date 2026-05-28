from dataclasses import dataclass


@dataclass
class ToolDTO:
    """Data Transfer Object for a single tool entry.

    Consumed exclusively by the view layer — no entity or repository
    types must leak into this dataclass.

    Attributes:
        title: Display name of the tool.
        description: Short description shown on the tool card.
        icon_path: Qt virtual path to the tool's icon resource.
        is_enabled: Whether the tool is currently enabled for use.
    """

    title: str
    description: str
    icon_path: str
    is_enabled: bool

from dataclasses import dataclass


@dataclass
class ToolEntity:
    """Canonical domain object representing a SyncDose tool/action.

    Populated by :class:`~repositories.tool.ToolRepository` and consumed by
    the tool ViewModel.

    Attributes:
        title: Display name and primary key of the tool.
        description: Short human-readable description shown on the tool card.
        icon_path: Qt virtual path to the tool's icon (e.g. ``":/icons/…"``).
        is_enabled: Whether the tool is active and should appear in the grid.
    """

    title: str
    description: str
    icon_path: str
    is_enabled: bool

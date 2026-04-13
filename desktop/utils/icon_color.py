"""View-layer utility for deriving icon background colors.

No data-layer type should import from this module — color is a view concern.
"""

import hashlib

from enums.device_type import DeviceType
from resources.colors import Palette

# Palette used for hash-based color derivation (devices, tools)
_ACCENT_PALETTE: list[str] = [
    Palette.CYAN_400,    # "#22D3EE"
    Palette.VIOLET_500,  # "#7B61FF"
    Palette.PINK_500,    # "#FF5C87"
    Palette.TEAL_400,    # "#00d4aa"
    Palette.GREEN_400,   # "#00E676"
    Palette.ORANGE_500,  # "#FF9800"
]

# Fixed semantic color per device-info card type
_DEVICE_TYPE_COLORS: dict[DeviceType, str] = {
    DeviceType.NAME:    Palette.CYAN_400,    # identity → primary accent
    DeviceType.OS:      Palette.VIOLET_500,  # system   → secondary accent
    DeviceType.IP:      Palette.TEAL_400,    # network  → teal
    DeviceType.BATTERY: Palette.GREEN_400,   # energy   → green
    DeviceType.STORAGE: Palette.PINK_500,    # storage  → tertiary accent
}


def icon_color_for_id(identifier: str) -> str:
    """Derive a deterministic accent color from any string identifier.

    Hashes ``identifier`` with MD5 and maps the result to an index in
    ``_ACCENT_PALETTE``.  The same identifier always produces the same color.

    Args:
        identifier: Any stable string (e.g. device ID, tool title).

    Returns:
        A hex color string from the accent palette.
    """
    index = int(hashlib.md5(identifier.encode()).hexdigest(), 16) % len(_ACCENT_PALETTE)
    return _ACCENT_PALETTE[index]


def icon_color_for_device_type(device_type: DeviceType) -> str:
    """Return the fixed icon color assigned to a given ``DeviceType``.

    Args:
        device_type: The type of the device-info card.

    Returns:
        A hex color string, falling back to ``CYAN_400`` for unknown types.
    """
    return _DEVICE_TYPE_COLORS.get(device_type, Palette.CYAN_400)

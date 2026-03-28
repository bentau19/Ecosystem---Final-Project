from enum import StrEnum


#  used for type checking
class ColorsEnum(StrEnum):
    pass


# Only hex values. No semantics. Add new hues here.
class Palette(ColorsEnum):
    DARK_900 = "#111827"  # Primary background color
    DARK_800 = "#141C26"  # Secondary background color

    GRAY_700 = "#1E3A4A"  # Border color for the default state
    GRAY_600 = "#162330"  # Border color for the hover state
    GRAY_500 = "#102a39"  # Border color for the active state
    GRAY_400 = "#0E4F5C"  # Border color for the hover state

    SLATE_500 = "#64748B"  # Primary text color
    SLATE_100 = "#E2E8F0"  # Secondary text color

    CYAN_400 = "#22D3EE"  # Primary accent color
    VIOLET_500 = "#7B61FF"  # Secondary accent color
    PINK_500 = "#FF5C87"  # Tertiary accent color

    GREEN_400 = "#00E676"  # Primary green color
    GREEN_200 = "#00C853"  # Secondary green color

    SILVER_300 = "#D4D7DD"  # Start color for the gradient
    SILVER_500 = "#6E7583"  # End color for the gradient

    PURPLE_500 = "#7B61FF"  # Primary purple color
    PURPLE_400 = "#6959F0"  # Secondary purple color


# What a color means. References layer 1. No component names here.

class Colors(ColorsEnum):
    SURFACE_PRIMARY = Palette.DARK_900  # Primary background color
    SURFACE_SECONDARY = Palette.DARK_800  # Secondary background color

    BORDER_DEFAULT = Palette.GRAY_700  # Border color for the default state
    BORDER_SUBTLE = Palette.GRAY_600  # Border color for the hover state
    BORDER_ACTIVE = Palette.GRAY_500  # Border color for the active state
    BORDER_HOVER = Palette.GRAY_400  # Border color for the hover state

    TEXT_PRIMARY = Palette.SLATE_100  # Primary text color
    TEXT_SECONDARY = Palette.SLATE_500  # Secondary text color

    ACCENT_PRIMARY = Palette.CYAN_400  # Primary accent color
    ACCENT_SECONDARY = Palette.VIOLET_500  # Secondary accent color
    ACCENT_TERTIARY = Palette.PINK_500  # Tertiary accent color

    GREEN = Palette.GREEN_400  # Primary green color


class SidebarColors(ColorsEnum):
    BACKGROUND = Colors.SURFACE_PRIMARY  # Background color of the sidebar
    BORDER = Colors.BORDER_DEFAULT  # Border color of the sidebar


class NavigationColors(ColorsEnum):
    ITEM_HOVER = Colors.BORDER_SUBTLE  # Border color when hovering over a navigation item
    ITEM_ACTIVE = Colors.BORDER_ACTIVE  # Border color when a navigation item is active


class DashboardColors(ColorsEnum):
    BORDER = Colors.ACCENT_PRIMARY  # Border color of the dashboard card
    CARD_BACKGROUND = Colors.SURFACE_SECONDARY  # Background color of the dashboard card
    CARD_BORDER = Colors.BORDER_DEFAULT  # Border color of the dashboard card


class StorageBarColors(ColorsEnum):
    GRADIENT_START = Palette.PURPLE_500  # Start color for the gradient
    GRADIENT_END = Palette.PURPLE_400
    # End color for the gradient


class BatteryBarColors(ColorsEnum):
    GRADIENT_START = Palette.GREEN_400  # Start color for the gradient
    GRADIENT_END = Palette.GREEN_200  # End color for the gradient


class InfoCardColors(ColorsEnum):
    BACKGROUND = Colors.SURFACE_SECONDARY  # Background color of the dashboard card
    BORDER = Colors.BORDER_DEFAULT  # Border color of the dashboard card
    TITLE = Colors.TEXT_SECONDARY  # Text color for the title of the info card
    BORDER_HOVER = Colors.BORDER_HOVER  # Border color when hovering over the info card


class ToolCardColors(ColorsEnum):
    BACKGROUND = Colors.SURFACE_SECONDARY  # Background color of the dashboard card
    BORDER = Colors.BORDER_DEFAULT  # Border color of the dashboard card
    TITLE = Colors.TEXT_PRIMARY  # Text color for the title of the tool card
    DESCRIPTION = Colors.TEXT_SECONDARY  # Text color for the description of the tool card
    BORDER_HOVER = Colors.ACCENT_PRIMARY  # Border color when hovering over the tool card


# Misc / special
class LogoColors(ColorsEnum):
    GRADIENT_START = Palette.SILVER_300  # Start color for the gradient
    GRADIENT_END = Palette.SILVER_500  # End color for the gradient

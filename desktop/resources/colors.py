from enum import StrEnum


#  used for type checking
class ColorsEnum(StrEnum):
    pass


# Only hex values. No semantics. Add new hues here.
class Palette(ColorsEnum):
    DARK_950 = "#0d1117"  # Deepest background surface (login left panel)
    DARK_900 = "#111827"  # Primary background color
    DARK_800 = "#141C26"  # Secondary background color
    DARK_750 = "#1a2535"  # Elevated card surface
    DARK_720 = "#1d2e42"  # Elevated card hover surface

    GRAY_720 = "#1e2530"  # Subtle divider / left-panel border
    GRAY_700 = "#1E3A4A"  # Border color for the default state
    GRAY_640 = "#243547"  # Card border default
    GRAY_600 = "#162330"  # Border color for the hover state
    GRAY_500 = "#102a39"  # Border color for the active state
    GRAY_400 = "#0E4F5C"  # Border color for the hover state

    SLATE_700 = "#374151"  # Very muted / footer text
    SLATE_600 = "#4A5568"  # Muted text (darker than SLATE_500)
    SLATE_500 = "#64748B"  # Primary text color
    SLATE_200 = "#c9d1d9"  # Light tertiary text
    SLATE_100 = "#E2E8F0"  # Secondary text color

    CYAN_400 = "#22D3EE"  # Primary accent color
    VIOLET_500 = "#7B61FF"  # Secondary accent color
    PINK_500 = "#FF5C87"  # Tertiary accent color

    TEAL_700 = "#009980"  # Teal accent — pressed / dark variant
    TEAL_400 = "#00d4aa"  # Teal accent — default
    TEAL_200 = "#00ffcc"  # Teal accent — hover / highlight

    GREEN_400 = "#00E676"  # Primary green color
    GREEN_200 = "#00C853"  # Secondary green color

    ORANGE_500 = "#FF9800"  # Orange accent color

    BLUE_700 = "#0369a1"  # Steel blue — device icon container background

    SILVER_300 = "#D4D7DD"  # Start color for the gradient
    SILVER_500 = "#6E7583"  # End color for the gradient
    SILVER_600 = "#6e7681"  # Warm muted text (slightly cooler than SILVER_500)

    PURPLE_500 = "#7B61FF"  # Primary purple color
    PURPLE_400 = "#6959F0"  # Secondary purple color

    # Muted deep-tint backgrounds for icon containers (dark-UI accent pits)
    CYAN_900   = "#0d2d36"  # deep cyan tint
    CYAN_800   = "#0f3d4f"  # mid cyan tint
    VIOLET_900 = "#1c1642"  # deep violet tint
    VIOLET_800 = "#221450"  # mid violet tint
    PINK_900   = "#2e1225"  # deep pink tint
    GREEN_900  = "#0d2c1a"  # deep green tint


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
    TEXT_TERTIARY = Palette.SLATE_200  # Light tertiary text
    TEXT_MUTED = Palette.SILVER_600  # Warm muted text

    ACCENT_PRIMARY = Palette.CYAN_400  # Primary accent color
    ACCENT_SECONDARY = Palette.VIOLET_500  # Secondary accent color
    ACCENT_TERTIARY = Palette.PINK_500  # Tertiary accent color
    ACCENT_TEAL = Palette.TEAL_400  # Teal accent (login / QR brackets)
    ACCENT_TEAL_HOVER = Palette.TEAL_200  # Teal accent hover state
    ACCENT_TEAL_PRESSED = Palette.TEAL_700  # Teal accent pressed state

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


class LoginColors(ColorsEnum):
    LEFT_PANEL_BG = Palette.DARK_950  # Left-panel body background
    LEFT_PANEL_BORDER = Palette.GRAY_720  # Left-panel right-edge separator
    CARD_BG = Palette.DARK_750  # Device card resting background
    CARD_BORDER = Palette.GRAY_640  # Device card resting border
    CARD_HOVER_BG = Palette.DARK_720  # Device card hover background
    ICON_BG = Palette.BLUE_700  # Device icon rounded-square background


# Misc / special
class LogoColors(ColorsEnum):
    GRADIENT_START = Palette.SILVER_300  # Start color for the gradient
    GRADIENT_END = Palette.SILVER_500  # End color for the gradient

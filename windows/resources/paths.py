from enum import StrEnum


# used for type checking
class PathsEnum(StrEnum):
    pass


# Icons
class Icons(PathsEnum):
    LOGO = ":/icons/logo.svg"
    SETTINGS = ":/icons/settings.svg"
    DASHBOARD = ":/icons/dashboard.svg"
    BATTERY = ":/icons/battery.svg"
    ANDROID = ":/icons/android.svg"
    STORAGE = ":/icons/storage.svg"
    SMARTPHONE = ":/icons/smartphone.svg"
    DISCONNECT = ":/icons/disconnect.svg"
    REFRESH = ":/icons/refresh.svg"


# Styles
class Styles(PathsEnum):
    DIVIDER = ":/styles/divider.qss"
    TOPBAR = ":/styles/topbar.qss"
    LOGO_WIDGET = ":/styles/logo_widget.qss"


# Navigation

class NavigationStyles(PathsEnum):
    SIDEBAR = ":/styles/navigation/sidebar.qss"
    CONTAINER = ":/styles/navigation/container.qss"
    ITEM = ":/styles/navigation/item.qss"


# Dashboard
class DashboardStyles(PathsEnum):
    INFO_CARD = ":/styles/dashboard/info_card.qss"
    TOOL_CARD = ":/styles/dashboard/tool_card.qss"
    BATTERY_INFO = ":/styles/dashboard/battery_info.qss"
    STORAGE_INFO = ":/styles/dashboard/storage_info.qss"
    DEVICE_STATUS_ROW = ":/styles/dashboard/device_status_row.qss"
    TOOLS_GRID = ":/styles/dashboard/tools_grid.qss"
    TOOLS_SECTION_HEADER = ":/styles/dashboard/tools_section_header.qss"


class LoginStyles(PathsEnum):
    LEFT_PANEL = ":/styles/login/left-panel.qss"
    RIGHT_PANEL = ":/styles/login/right-panel.qss"


# Indicators
class IndicatorStyles(PathsEnum):
    CONNECTION_PILL = ":/styles/indicators/connection_pill.qss"

from enum import StrEnum


class PathsEnum(StrEnum):
    """Base marker class for all Qt virtual-path enums.

    Used as a type bound so any path enum can be passed where a
    ``PathsEnum`` is expected without coupling to a specific sub-class.
    """


class Icons(PathsEnum):
    """Qt virtual paths to bundled SVG icon assets (registered in ``syncdose.qrc``)."""

    LOGO = ":/icons/logo.svg"
    BACKUP_PROGRESS = ":/icons/backup_progress.svg"
    SETTINGS = ":/icons/settings.svg"
    DASHBOARD = ":/icons/dashboard.svg"
    BATTERY = ":/icons/battery.svg"
    ANDROID = ":/icons/android.svg"
    STORAGE = ":/icons/storage.svg"
    SMARTPHONE = ":/icons/smartphone.svg"
    DISCONNECT = ":/icons/disconnect.svg"
    REFRESH = ":/icons/refresh.svg"


class Styles(PathsEnum):
    """Qt virtual paths to top-level QSS stylesheets."""

    DIVIDER = ":/styles/divider.qss"
    TOPBAR = ":/styles/topbar.qss"
    LOGO_WIDGET = ":/styles/logo_widget.qss"
    TRAY_MENU = ":/styles/tray-menu.qss"


class NavigationStyles(PathsEnum):
    """Qt virtual paths to navigation-widget QSS stylesheets."""

    SIDEBAR = ":/styles/navigation/sidebar.qss"
    CONTAINER = ":/styles/navigation/container.qss"
    ITEM = ":/styles/navigation/item.qss"


class DashboardStyles(PathsEnum):
    """Qt virtual paths to dashboard-widget QSS stylesheets."""

    INFO_CARD = ":/styles/dashboard/info_card.qss"
    TOOL_CARD = ":/styles/dashboard/tool_card.qss"
    BATTERY_INFO = ":/styles/dashboard/battery_info.qss"
    STORAGE_INFO = ":/styles/dashboard/storage_info.qss"
    DEVICE_STATUS_ROW = ":/styles/dashboard/device_status_row.qss"
    TOOLS_GRID = ":/styles/dashboard/tools_grid.qss"
    TOOLS_SECTION_HEADER = ":/styles/dashboard/tools_section_header.qss"


class LoginStyles(PathsEnum):
    """Qt virtual paths to login-screen QSS stylesheets."""

    LEFT_PANEL = ":/styles/login/left-panel.qss"
    RIGHT_PANEL = ":/styles/login/right-panel.qss"


class IndicatorStyles(PathsEnum):
    """Qt virtual paths to indicator-widget QSS stylesheets."""

    CONNECTION_PILL = ":/styles/indicators/connection_pill.qss"


class ToastStyles(PathsEnum):
    """Qt virtual paths to toast-widget QSS stylesheets."""

    FILE_RECEIVED = ":/styles/toasts/file-received.qss"


class LoadingStyles(PathsEnum):
    """Qt virtual paths to loading-widget QSS stylesheets."""

    OVERLAY = ":/styles/loading/overlay.qss"


class BackupStyles(PathsEnum):
    """Qt virtual paths to backup-widget QSS stylesheets."""

    REVIEW              = ":/styles/backup/backup-review.qss"
    PROGRESS            = ":/styles/backup/backup-progress.qss"
    CLASSIFICATION_REVIEW = ":/styles/backup/backup-classification-review.qss"


class SettingsStyles(PathsEnum):
    """Qt virtual paths to settings-screen QSS stylesheets."""

    SETTINGS_CONTENT = ":/styles/settings/settings.qss"

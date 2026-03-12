from enum import StrEnum


class Resources(StrEnum):
    LOGO_ICON_PATH = ":/icons/logo.svg"
    SETTINGS_ICON_PATH = ":/icons/settings.svg"
    DASHBOARD_ICON_PATH = ":/icons/dashboard.svg"
    LIGHTNING_ICON_PATH = ":/icons/lightning.svg"

    LOGO_WIDGET_QSS_PATH = ":/styles/logo_widget.qss"
    SIDEBAR_QSS_PATH = ":/styles/sidebar.qss"
    NAVIGATION_CONTAINER_QSS_PATH = ":/styles/navigation_container.qss"
    NAVIGATION_ITEM_QSS_PATH = ":/styles/navigation_item.qss"
    DIVIDER_QSS_PATH = ":/styles/divider.qss"
    CONNECTION_PILL_QSS_PATH = ":/styles/connection_pill.qss"
    BATTERY_CARD_QSS_PATH = ":/styles/battery_card.qss"

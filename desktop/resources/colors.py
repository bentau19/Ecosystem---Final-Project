from enum import StrEnum


class ColorsEnum(StrEnum):
    """Base marker class for all color enum families.

    Used as a type bound in :func:`~utils.styles.load_stylesheet` so that
    any color enum — ``Palette``, ``Colors``, or a component sub-class — can
    be passed interchangeably.
    """


class Palette(ColorsEnum):
    """Raw hex color values with no semantic meaning.

    Layer 1 of the design-token hierarchy.  Only add new hues here; semantic
    aliases belong in :class:`Colors` or a component-specific class.
    """
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


class Colors(ColorsEnum):
    """Semantic color aliases that reference :class:`Palette` entries.

    Layer 2 of the design-token hierarchy.  Names describe *purpose*
    (e.g. ``TEXT_PRIMARY``), not appearance.  No component names here.
    """
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
    """Component-scoped color tokens for the navigation sidebar."""

    BACKGROUND = Colors.SURFACE_PRIMARY  # Background color of the sidebar
    BORDER = Colors.BORDER_DEFAULT  # Border color of the sidebar


class NavigationColors(ColorsEnum):
    """Component-scoped color tokens for individual navigation items."""

    ITEM_HOVER = Colors.BORDER_SUBTLE  # Border color when hovering over a navigation item
    ITEM_ACTIVE = Colors.BORDER_ACTIVE  # Border color when a navigation item is active


class DashboardColors(ColorsEnum):
    """Component-scoped color tokens for dashboard-level containers."""

    BORDER          = Colors.ACCENT_PRIMARY     # Border color of the dashboard card
    CARD_BACKGROUND = Colors.SURFACE_SECONDARY  # Background color of the dashboard card
    CARD_BORDER     = Colors.BORDER_DEFAULT     # Border color of the dashboard card
    TAG_BACKGROUND  = "#1E2A38"                 # Tools-section tag pill background


class StorageBarColors(ColorsEnum):
    """Component-scoped color tokens for the storage progress bar gradient."""

    GRADIENT_START = Palette.PURPLE_500  # Start color for the gradient
    GRADIENT_END = Palette.PURPLE_400    # End color for the gradient


class BatteryBarColors(ColorsEnum):
    """Component-scoped color tokens for the battery progress bar gradient."""

    GRADIENT_START = Palette.GREEN_400  # Start color for the gradient
    GRADIENT_END = Palette.GREEN_200  # End color for the gradient


class InfoCardColors(ColorsEnum):
    """Component-scoped color tokens for device info cards on the dashboard."""

    BACKGROUND = Colors.SURFACE_SECONDARY  # Background color of the dashboard card
    BORDER = Colors.BORDER_DEFAULT  # Border color of the dashboard card
    TITLE = Colors.TEXT_SECONDARY  # Text color for the title of the info card
    BORDER_HOVER = Colors.BORDER_HOVER  # Border color when hovering over the info card
    ICON_BG = Palette.CYAN_800  # Icon container background tint


class ToolCardColors(ColorsEnum):
    """Component-scoped color tokens for tool cards on the dashboard."""

    BACKGROUND = Colors.SURFACE_SECONDARY  # Background color of the dashboard card
    BORDER = Colors.BORDER_DEFAULT  # Border color of the dashboard card
    TITLE = Colors.TEXT_PRIMARY  # Text color for the title of the tool card
    DESCRIPTION = Colors.TEXT_SECONDARY  # Text color for the description of the tool card
    BORDER_HOVER = Colors.ACCENT_PRIMARY  # Border color when hovering over the tool card


class LoginColors(ColorsEnum):
    """Component-scoped color tokens for the login screen panels and device cards."""

    LEFT_PANEL_BG     = Palette.DARK_950   # Left-panel body background
    LEFT_PANEL_BORDER = Palette.GRAY_720   # Left-panel right-edge separator
    CARD_BG           = Palette.DARK_750   # Device card resting background
    CARD_BORDER       = Palette.GRAY_640   # Device card resting border
    CARD_HOVER_BG     = Palette.DARK_720   # Device card hover background
    ICON_BG           = Palette.BLUE_700   # Device icon rounded-square background
    # Right-panel extended tokens
    TEXT_FAINT        = Palette.SLATE_600  # Device timestamp, idle badge, footer link
    TEXT_FOOTER       = Palette.SLATE_700  # Very muted footer body text
    ACCENT_HOVER      = "#67E8F9"          # Lighter cyan for ConnectBtn hover (sky-300)


class LogoColors(ColorsEnum):
    """Component-scoped color tokens for the logo gradient text label."""

    GRADIENT_START = Palette.SILVER_300  # Start color for the gradient
    GRADIENT_END = Palette.SILVER_500  # End color for the gradient


class FileReceivedToastColors(ColorsEnum):
    """Component-scoped color tokens for the file-received toast notification."""

    BACKGROUND         = Palette.DARK_750   # Elevated card surface
    BORDER             = Palette.GRAY_640   # Card border default
    TITLE              = Palette.SLATE_100  # Primary heading text
    FILENAME           = Palette.SLATE_500  # Secondary / muted filename text
    ICON_BG            = Palette.CYAN_900   # Deep cyan tint — icon circle bg
    ICON_BORDER        = Palette.CYAN_800   # Mid cyan tint — icon circle border
    ICON_COLOR         = Palette.CYAN_400   # Cyan accent — icon character
    DOWNLOAD_BTN       = Palette.CYAN_400   # Primary action text (default)
    DOWNLOAD_BTN_HOVER = Palette.TEAL_200   # Primary action text (hover)
    CANCEL_BTN         = Palette.SLATE_500  # Neutral secondary text (default)
    CANCEL_BTN_HOVER   = Palette.SLATE_100  # Neutral secondary text (hover)


class HandlerDialogColors(ColorsEnum):
    """Component-scoped color tokens for file-handler error dialogs.

    Accent-derived tokens (strip background tint, button hover/pressed states)
    are dynamic per dialog variant and are injected separately in the widget's
    ``_setup_style`` method — they do not live here.
    """

    BACKGROUND       = Palette.DARK_900   # Dialog body background surface
    BORDER           = Palette.GRAY_700   # Dialog border
    TEXT_PRIMARY     = Palette.SLATE_100  # Bold heading text
    TEXT_SECONDARY   = Palette.SLATE_500  # Explanatory body text
    BTN_GRADIENT_END = "#0891b2"          # Try Again gradient end (sky-600)
    ACCENT           = Palette.CYAN_400   # Icon circle and primary button accent


class TopbarColors(ColorsEnum):
    """Component-scoped color tokens for the top navigation bar (dark mode)."""

    BACKGROUND     = Palette.DARK_950   # #0d1117 — deepest bg, matches login left-panel
    TITLE_COLOR    = Palette.SLATE_100  # #E2E8F0 near-white title
    SUBTITLE_COLOR = Palette.SLATE_500  # #64748B muted subtitle
    # Disconnect button — danger red, theme-invariant
    BTN_BG_0    = "#7F1D1D"
    BTN_BG_1    = "#991B1B"
    BTN_BORDER  = "#DC2626"
    BTN_COLOR   = "#FCA5A5"
    BTN_HOVER_0 = "#991B1B"
    BTN_HOVER_1 = "#B91C1C"
    BTN_PRESSED = "#7F1D1D"


# ══════════════════════════════════════════════════════════════════════════════
# Light-mode palette & semantic tokens
# ══════════════════════════════════════════════════════════════════════════════

class LightPalette(ColorsEnum):
    """Raw hex color values for the light theme.

    Mirror of :class:`Palette` — identical member names, light-appropriate values.
    Layer 1 of the light design-token hierarchy.
    """

    DARK_950 = "#FFFFFF"   # Deepest background surface (login left panel)
    DARK_900 = "#F8FAFC"   # Primary background color
    DARK_800 = "#F1F5F9"   # Secondary background color
    DARK_750 = "#E8F0F8"   # Elevated card surface
    DARK_720 = "#DDE8F4"   # Elevated card hover surface

    GRAY_720 = "#CBD5E1"   # Subtle divider / left-panel border
    GRAY_700 = "#94A3B8"   # Border color for the default state
    GRAY_640 = "#CBD5E1"   # Card border default
    GRAY_600 = "#BAC6D6"   # Border color for the hover state
    GRAY_500 = "#A0B0C4"   # Border color for the active state
    GRAY_400 = "#0E4F5C"   # Border color for the hover state (accent-tinted, same as dark)

    SLATE_700 = "#94A3B8"  # Very muted / footer text
    SLATE_600 = "#64748B"  # Muted text
    SLATE_500 = "#475569"  # Primary text color (inverted — dark on light)
    SLATE_200 = "#1E293B"  # Light tertiary text (inverted)
    SLATE_100 = "#0F172A"  # Secondary text color (inverted — near-black)

    # Accent hues are identical in both themes
    CYAN_400   = "#22D3EE"
    VIOLET_500 = "#7B61FF"
    PINK_500   = "#FF5C87"

    TEAL_700 = "#009980"
    TEAL_400 = "#00d4aa"
    TEAL_200 = "#00ffcc"

    GREEN_400 = "#00E676"
    GREEN_200 = "#00C853"

    ORANGE_500 = "#FF9800"

    BLUE_700 = "#0369a1"

    SILVER_300 = "#D4D7DD"
    SILVER_500 = "#6E7583"
    SILVER_600 = "#6e7681"

    PURPLE_500 = "#7B61FF"
    PURPLE_400 = "#6959F0"

    # Light-mode tint backgrounds for icon containers (inverted from dark)
    CYAN_900   = "#D0F4FA"  # Light cyan tint — icon container bg
    CYAN_800   = "#A5E8F5"  # Mid cyan tint — icon container border
    VIOLET_900 = "#EDE9FE"
    VIOLET_800 = "#DDD6FE"
    PINK_900   = "#FCE7F3"
    GREEN_900  = "#DCFCE7"


class LightColors(ColorsEnum):
    """Semantic color aliases for the light theme.

    Mirror of :class:`Colors` — identical member names, resolved via :class:`LightPalette`.
    Layer 2 of the light design-token hierarchy.
    """

    SURFACE_PRIMARY   = LightPalette.DARK_900
    SURFACE_SECONDARY = LightPalette.DARK_800

    BORDER_DEFAULT = LightPalette.GRAY_700
    BORDER_SUBTLE  = LightPalette.GRAY_600
    BORDER_ACTIVE  = LightPalette.GRAY_500
    BORDER_HOVER   = LightPalette.GRAY_400

    TEXT_PRIMARY   = LightPalette.SLATE_100
    TEXT_SECONDARY = LightPalette.SLATE_500
    TEXT_TERTIARY  = LightPalette.SLATE_200
    TEXT_MUTED     = LightPalette.SILVER_600

    ACCENT_PRIMARY      = LightPalette.CYAN_400
    ACCENT_SECONDARY    = LightPalette.VIOLET_500
    ACCENT_TERTIARY     = LightPalette.PINK_500
    ACCENT_TEAL         = LightPalette.TEAL_400
    ACCENT_TEAL_HOVER   = LightPalette.TEAL_200
    ACCENT_TEAL_PRESSED = LightPalette.TEAL_700

    GREEN = LightPalette.GREEN_400


# ── Light component color tokens ───────────────────────────────────────────────

class LightSidebarColors(ColorsEnum):
    """Light-mode component tokens for the navigation sidebar."""

    BACKGROUND = LightColors.SURFACE_PRIMARY
    BORDER     = LightColors.BORDER_DEFAULT


class LightNavigationColors(ColorsEnum):
    """Light-mode component tokens for individual navigation items."""

    ITEM_HOVER  = LightColors.BORDER_SUBTLE
    ITEM_ACTIVE = LightColors.BORDER_ACTIVE


class LightDashboardColors(ColorsEnum):
    """Light-mode component tokens for dashboard-level containers."""

    BORDER          = LightColors.ACCENT_PRIMARY
    CARD_BACKGROUND = LightColors.SURFACE_SECONDARY
    CARD_BORDER     = LightColors.BORDER_DEFAULT
    TAG_BACKGROUND  = LightPalette.DARK_800   # #F1F5F9 — light equivalent of tag pill


class LightStorageBarColors(ColorsEnum):
    """Light-mode component tokens for the storage progress bar (gradient unchanged)."""

    GRADIENT_START = Palette.PURPLE_500
    GRADIENT_END   = Palette.PURPLE_400


class LightBatteryBarColors(ColorsEnum):
    """Light-mode component tokens for the battery progress bar (gradient unchanged)."""

    GRADIENT_START = Palette.GREEN_400
    GRADIENT_END   = Palette.GREEN_200


class LightInfoCardColors(ColorsEnum):
    """Light-mode component tokens for device info cards on the dashboard."""

    BACKGROUND   = LightColors.SURFACE_SECONDARY
    BORDER       = LightColors.BORDER_DEFAULT
    TITLE        = LightColors.TEXT_SECONDARY
    BORDER_HOVER = LightColors.BORDER_HOVER


class LightToolCardColors(ColorsEnum):
    """Light-mode component tokens for tool cards on the dashboard."""

    BACKGROUND   = LightColors.SURFACE_SECONDARY
    BORDER       = LightColors.BORDER_DEFAULT
    TITLE        = LightColors.TEXT_PRIMARY
    DESCRIPTION  = LightColors.TEXT_SECONDARY
    BORDER_HOVER = LightColors.ACCENT_PRIMARY


class LightLoginColors(ColorsEnum):
    """Light-mode component tokens for the login screen panels and device cards."""

    LEFT_PANEL_BG     = LightPalette.DARK_950   # pure white left panel
    LEFT_PANEL_BORDER = LightPalette.GRAY_720   # cool gray separator
    CARD_BG           = LightPalette.DARK_750   # light blue-tinted card bg
    CARD_BORDER       = LightPalette.GRAY_640   # light gray card border
    CARD_HOVER_BG     = LightPalette.DARK_720   # slightly deeper on hover
    ICON_BG           = Palette.BLUE_700        # icon container bg (unchanged)
    # Right-panel extended tokens
    TEXT_FAINT        = LightPalette.SLATE_600  # device timestamp, idle badge, footer link
    TEXT_FOOTER       = LightPalette.SLATE_700  # very muted footer body text
    ACCENT_HOVER      = "#67E8F9"               # sky-300 lighter cyan — theme-invariant


class LightLogoColors(ColorsEnum):
    """Light-mode component tokens for the logo gradient (unchanged — looks good on both)."""

    GRADIENT_START = Palette.SILVER_300
    GRADIENT_END   = Palette.SILVER_500


class LightFileReceivedToastColors(ColorsEnum):
    """Light-mode component tokens for the file-received toast notification."""

    BACKGROUND         = LightPalette.DARK_750
    BORDER             = LightPalette.GRAY_640
    TITLE              = LightPalette.SLATE_100
    FILENAME           = LightPalette.SLATE_500
    ICON_BG            = LightPalette.CYAN_900
    ICON_BORDER        = LightPalette.CYAN_800
    ICON_COLOR         = Palette.CYAN_400
    DOWNLOAD_BTN       = Palette.CYAN_400
    DOWNLOAD_BTN_HOVER = Palette.TEAL_200
    CANCEL_BTN         = LightPalette.SLATE_500
    CANCEL_BTN_HOVER   = LightPalette.SLATE_100


class LightHandlerDialogColors(ColorsEnum):
    """Light-mode component tokens for file-handler error dialogs."""

    BACKGROUND       = LightPalette.DARK_900
    BORDER           = LightPalette.GRAY_700
    TEXT_PRIMARY     = LightPalette.SLATE_100
    TEXT_SECONDARY   = LightPalette.SLATE_500
    BTN_GRADIENT_END = "#0891b2"  # sky-600 — works on both themes


class LightTopbarColors(ColorsEnum):
    """Light-mode component tokens for the top navigation bar."""

    BACKGROUND     = LightPalette.DARK_900   # #F8FAFC clean light surface
    TITLE_COLOR    = LightPalette.SLATE_100  # #0F172A near-black title
    SUBTITLE_COLOR = LightPalette.SLATE_500  # #475569 muted subtitle
    # Disconnect button — same danger red on both themes
    BTN_BG_0    = "#7F1D1D"
    BTN_BG_1    = "#991B1B"
    BTN_BORDER  = "#DC2626"
    BTN_COLOR   = "#FCA5A5"
    BTN_HOVER_0 = "#991B1B"
    BTN_HOVER_1 = "#B91C1C"
    BTN_PRESSED = "#7F1D1D"


class LoadingOverlayColors(ColorsEnum):
    """Component-scoped color tokens for the loading overlay (dark mode)."""

    TEXT = Palette.SLATE_500  # Muted secondary text below the spinner


class LightLoadingOverlayColors(ColorsEnum):
    """Component-scoped color tokens for the loading overlay (light mode)."""

    TEXT = LightPalette.SLATE_500  # Muted secondary text below the spinner


# ── Backup Review colors ───────────────────────────────────────────────────────

class BackupReviewColors(ColorsEnum):
    """Component-scoped color tokens for the backup file review dialog (dark mode).

    Token names match the ``{{PLACEHOLDER}}`` keys used in
    ``resources/styles/backup/backup-review.qss``.
    """

    BACKGROUND    = Palette.DARK_900   # Dialog body surface
    BORDER        = Palette.GRAY_700   # Dialog border + dividers
    TEXT_PRIMARY  = Palette.SLATE_100  # Heading / filename text
    TEXT_SECONDARY = Palette.SLATE_500  # Subtitle / meta / summary text
    ROW_BG        = Palette.DARK_800   # File row default background
    ROW_BORDER    = Palette.GRAY_700   # File row default border
    ROW_HOVER     = Palette.DARK_750   # File row hover background
    KEEP_BG       = Palette.GREEN_900  # Row bg when decision = "keep"
    KEEP_BORDER   = Palette.GREEN_400  # Row / button border when kept
    KEEP_TEXT     = Palette.GREEN_400  # Keep button active text
    DELETE_BG     = Palette.PINK_900   # Row bg when decision = "delete"
    DELETE_BORDER = Palette.PINK_500   # Row / button border when deleted
    DELETE_TEXT   = Palette.PINK_500   # Delete button active text
    ICON_BG       = Palette.CYAN_900   # FileThumbFallback circle background
    ICON_BORDER   = Palette.CYAN_800   # FileThumbFallback circle border
    ICON_TEXT     = Palette.CYAN_400   # FileThumbFallback text + Apply button gradient start


class LightBackupReviewColors(ColorsEnum):
    """Light-mode component tokens for the backup file review dialog.

    Mirror of :class:`BackupReviewColors` — identical member names, light-appropriate values.
    """

    BACKGROUND    = LightPalette.DARK_900   # Dialog body surface
    BORDER        = LightPalette.GRAY_700   # Dialog border + dividers
    TEXT_PRIMARY  = LightPalette.SLATE_100  # Heading / filename text
    TEXT_SECONDARY = LightPalette.SLATE_500  # Subtitle / meta / summary text
    ROW_BG        = LightPalette.DARK_800   # File row default background
    ROW_BORDER    = LightPalette.GRAY_700   # File row default border
    ROW_HOVER     = LightPalette.DARK_750   # File row hover background
    KEEP_BG       = LightPalette.GREEN_900  # Row bg when decision = "keep"
    KEEP_BORDER   = Palette.GREEN_400       # Row / button border when kept (accent-invariant)
    KEEP_TEXT     = Palette.GREEN_400       # Keep button active text (accent-invariant)
    DELETE_BG     = LightPalette.PINK_900   # Row bg when decision = "delete"
    DELETE_BORDER = Palette.PINK_500        # Row / button border when deleted (accent-invariant)
    DELETE_TEXT   = Palette.PINK_500        # Delete button active text (accent-invariant)
    ICON_BG       = LightPalette.CYAN_900   # FileThumbFallback circle background
    ICON_BORDER   = LightPalette.CYAN_800   # FileThumbFallback circle border
    ICON_TEXT     = Palette.CYAN_400        # FileThumbFallback text + Apply button (accent-invariant)


# ── Backup Classification Review colors ────────────────────────────────────────

class BackupClassificationReviewColors(ColorsEnum):
    """Component-scoped color tokens for the single-file confidence review
    dialog (dark mode).

    Token names match the ``{{PLACEHOLDER}}`` keys used in
    ``resources/styles/backup/backup-confidence-review.qss``.
    """

    BACKGROUND     = Palette.DARK_900   # Dialog body surface
    BORDER         = Palette.GRAY_700   # Dialog border + dividers
    TEXT_PRIMARY   = Palette.SLATE_100  # Heading / filename text
    TEXT_SECONDARY = Palette.SLATE_500  # Subtitle / meta text
    KEEP_BG        = Palette.GREEN_900  # Keep button active background
    KEEP_BORDER    = Palette.GREEN_400  # Keep button border (default + active)
    KEEP_TEXT      = Palette.GREEN_400  # Keep button text
    REMOVE_BG      = Palette.PINK_900   # Remove button active background
    REMOVE_BORDER  = Palette.PINK_500   # Remove button border (default + active)
    REMOVE_TEXT    = Palette.PINK_500   # Remove button text
    ICON_BG        = Palette.CYAN_900   # Thumbnail-fallback circle background
    ICON_BORDER    = Palette.CYAN_800   # Thumbnail-fallback circle border
    ICON_TEXT      = Palette.CYAN_400   # Thumbnail-fallback text
    WARNING_TEXT   = Palette.ORANGE_500  # "Needs review" confidence badge text
    KEEP_ALL_BG     = Palette.TEAL_700   # KeepAll button hover/pressed background
    KEEP_ALL_BORDER = Palette.TEAL_400   # KeepAll button border
    KEEP_ALL_TEXT   = Palette.TEAL_400   # KeepAll button text


class LightBackupClassificationReviewColors(ColorsEnum):
    """Light-mode component tokens for the single-file confidence review dialog.

    Mirror of :class:`BackupClassificationReviewColors` — identical member
    names, light-appropriate values.
    """

    BACKGROUND     = LightPalette.DARK_900   # Dialog body surface
    BORDER         = LightPalette.GRAY_700   # Dialog border + dividers
    TEXT_PRIMARY   = LightPalette.SLATE_100  # Heading / filename text
    TEXT_SECONDARY = LightPalette.SLATE_500  # Subtitle / meta text
    KEEP_BG        = LightPalette.GREEN_900  # Keep button active background
    KEEP_BORDER    = Palette.GREEN_400       # Keep button border (accent-invariant)
    KEEP_TEXT      = Palette.GREEN_400       # Keep button text (accent-invariant)
    REMOVE_BG      = LightPalette.PINK_900   # Remove button active background
    REMOVE_BORDER  = Palette.PINK_500        # Remove button border (accent-invariant)
    REMOVE_TEXT    = Palette.PINK_500        # Remove button text (accent-invariant)
    ICON_BG        = LightPalette.CYAN_900   # Thumbnail-fallback circle background
    ICON_BORDER    = LightPalette.CYAN_800   # Thumbnail-fallback circle border
    ICON_TEXT      = Palette.CYAN_400        # Thumbnail-fallback text (accent-invariant)
    WARNING_TEXT   = Palette.ORANGE_500       # "Needs review" confidence badge text (accent-invariant)
    KEEP_ALL_BG     = Palette.TEAL_700        # KeepAll button hover/pressed background (accent-invariant)
    KEEP_ALL_BORDER = Palette.TEAL_400        # KeepAll button border (accent-invariant)
    KEEP_ALL_TEXT   = Palette.TEAL_400        # KeepAll button text (accent-invariant)


# ── Backup Progress colors ─────────────────────────────────────────────────────

class BackupProgressColors(ColorsEnum):
    """Component-scoped color tokens for the backup progress window (dark mode).

    Token names match the ``{{PLACEHOLDER}}`` keys used in
    ``resources/styles/backup/backup-progress.qss``.
    """

    BACKGROUND          = Palette.DARK_900   # Window body surface
    SURFACE             = Palette.DARK_800   # Elevated card surface (overall section)
    BORDER              = Palette.GRAY_700   # Borders + dividers
    ROW_BG              = Palette.DARK_800   # File row default background
    ROW_BORDER          = Palette.GRAY_700   # File row default border
    ROW_ACTIVE_BG       = Palette.CYAN_900   # File row bg when actively syncing
    ROW_ACTIVE_BORDER   = Palette.CYAN_800   # File row border when actively syncing
    TEXT_PRIMARY        = Palette.SLATE_100  # Primary text (filenames, %)
    TEXT_SECONDARY      = Palette.SLATE_500  # Secondary text (sizes, stats)
    PROGRESS_TRACK      = Palette.GRAY_720   # Empty portion of progress bar track
    PROGRESS_FILL       = Palette.CYAN_400   # Progress bar gradient start
    PROGRESS_FILL_END   = Palette.TEAL_400   # Progress bar gradient end
    STATUS_QUEUED_TEXT  = Palette.SLATE_600  # "Queued" badge text
    STATUS_ACTIVE_BG    = Palette.CYAN_900   # "Syncing" badge + row background
    STATUS_ACTIVE_TEXT  = Palette.CYAN_400   # "Syncing" badge text + speed label
    STATUS_DONE_BG      = Palette.GREEN_900  # "Done" badge + row background
    STATUS_DONE_TEXT    = Palette.GREEN_400  # "Done" badge text + row border
    STATUS_FAILED_BG    = Palette.PINK_900   # "Failed" badge + row background
    STATUS_FAILED_TEXT  = Palette.PINK_500   # "Failed" badge text + row border
    BTN_PAUSE_BORDER    = Palette.GRAY_700   # Pause button border (default)
    BTN_PAUSE_TEXT      = Palette.SLATE_100  # Pause button text (default)
    BTN_CANCEL_BORDER   = Palette.PINK_500   # Cancel button border
    BTN_CANCEL_TEXT     = Palette.PINK_500   # Cancel button text


class LightBackupProgressColors(ColorsEnum):
    """Light-mode component tokens for the backup progress window.

    Mirror of :class:`BackupProgressColors` — identical member names, light-appropriate values.
    Accent-derived tokens (progress fill, status colours) are theme-invariant.
    """

    BACKGROUND          = LightPalette.DARK_900   # Window body surface
    SURFACE             = LightPalette.DARK_800   # Elevated card surface
    BORDER              = LightPalette.GRAY_700   # Borders + dividers
    ROW_BG              = LightPalette.DARK_800   # File row default background
    ROW_BORDER          = LightPalette.GRAY_700   # File row default border
    ROW_ACTIVE_BG       = LightPalette.CYAN_900   # File row bg when actively syncing
    ROW_ACTIVE_BORDER   = LightPalette.CYAN_800   # File row border when actively syncing
    TEXT_PRIMARY        = LightPalette.SLATE_100  # Primary text
    TEXT_SECONDARY      = LightPalette.SLATE_500  # Secondary text
    PROGRESS_TRACK      = LightPalette.GRAY_720   # Empty portion of progress bar track
    PROGRESS_FILL       = Palette.CYAN_400        # Progress bar gradient start (invariant)
    PROGRESS_FILL_END   = Palette.TEAL_400        # Progress bar gradient end (invariant)
    STATUS_QUEUED_TEXT  = LightPalette.SLATE_600  # "Queued" badge text
    STATUS_ACTIVE_BG    = LightPalette.CYAN_900   # "Syncing" badge + row background
    STATUS_ACTIVE_TEXT  = Palette.CYAN_400        # "Syncing" badge text (invariant)
    STATUS_DONE_BG      = LightPalette.GREEN_900  # "Done" badge + row background
    STATUS_DONE_TEXT    = Palette.GREEN_400        # "Done" badge text (invariant)
    STATUS_FAILED_BG    = LightPalette.PINK_900   # "Failed" badge + row background
    STATUS_FAILED_TEXT  = Palette.PINK_500        # "Failed" badge text (invariant)
    BTN_PAUSE_BORDER    = LightPalette.GRAY_700   # Pause button border (default)
    BTN_PAUSE_TEXT      = LightPalette.SLATE_100  # Pause button text (default)
    BTN_CANCEL_BORDER   = Palette.PINK_500        # Cancel button border (invariant)
    BTN_CANCEL_TEXT     = Palette.PINK_500        # Cancel button text (invariant)

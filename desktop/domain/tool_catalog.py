"""Canonical catalog of SyncDose tools.

Single source of truth for the stable tool titles and the default seed list.
Imported by the tool repository (seeding ``tools.json``), the tool viewmodel
(dispatching a toggle to the matching background service) and the dashboard
grid (click / hint behaviour per tool).  Kept dependency-light so it never
forms an import cycle with the repository or viewmodel layers.
"""

from domain.entities.tool import ToolEntity
from resources.paths import Icons

# Stable tool titles — used as the repository primary key and as identifiers
# for per-tool behaviour in the viewmodel and grid.  Changing a title is a
# data migration (it is the key), so treat these as constants.
TITLE_SEND_FILE = "Send File to Phone"
TITLE_VIRTUAL_DRIVE = "Virtual Drive"
TITLE_CLIPBOARD = "Clipboard Sync"
TITLE_WEBCAM = "Webcam"
TITLE_BACKUP = "Backup"

# Titles of the four background "feature" tools whose enabled state gates a
# service and is synced bidirectionally with the phone (Send File is an action,
# not a feature, so it is excluded here).
FEATURE_TITLES: tuple[str, ...] = (
    TITLE_VIRTUAL_DRIVE,
    TITLE_CLIPBOARD,
    TITLE_WEBCAM,
    TITLE_BACKUP,
)

# Seed tools written to tools.json on first run.  Every tool defaults enabled
# (opt-out), matching the previous settings behaviour.
SEED_TOOLS: list[ToolEntity] = [
    ToolEntity(
        TITLE_SEND_FILE,
        "Send any file from your PC directly to your phone.",
        Icons.SMARTPHONE.value,
        True,
    ),
    ToolEntity(
        TITLE_VIRTUAL_DRIVE,
        "Mount your phone as a Windows drive letter whenever a device is "
        "connected, so you can browse phone files directly in Explorer.",
        Icons.STORAGE.value,
        True,
    ),
    ToolEntity(
        TITLE_CLIPBOARD,
        "Keep the clipboard in sync between this PC and your phone while a "
        "device is connected.",
        Icons.CLIPBOARD.value,
        True,
    ),
    ToolEntity(
        TITLE_WEBCAM,
        "Let your phone stream its camera to a virtual webcam that other apps "
        "(Zoom, OBS, …) can use.",
        Icons.WEBCAM.value,
        True,
    ),
    ToolEntity(
        TITLE_BACKUP,
        "Allow your phone to back up photos and files to this PC. Disabling "
        "this prevents new backup sessions from starting.",
        Icons.BACKUP_PROGRESS.value,
        True,
    ),
]

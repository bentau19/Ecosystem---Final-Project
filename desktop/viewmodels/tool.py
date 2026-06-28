from dataclasses import replace

from PySide6.QtCore import QObject, Signal, Slot

from domain.dto.tool import ToolDTO
from domain.entities.tool import ToolEntity
from domain.tool_catalog import (
    FEATURE_TITLES,
    TITLE_BACKUP,
    TITLE_CLIPBOARD,
    TITLE_VIRTUAL_DRIVE,
    TITLE_WEBCAM,
)
from services.backup import BackupService
from services.clipboard import ClipboardService
from services.connectivity import ConnectivityService
from services.settings import SettingsService
from services.tool import ToolService
from services.virtual_drive import VirtualDriveService
from services.webcam import WebcamService
from viewmodels.device import DeviceViewModel


class ToolViewModel(QObject):
    """ViewModel and coordinator for the dashboard tools grid.

    Presents every tool as a view-ready :class:`~domain.dto.tool.ToolDTO`, and
    owns the side effects of enabling/disabling the four background "feature"
    tools (Virtual Drive, Clipboard, Webcam, Backup): applying the new state to
    the matching service, wiring the Virtual Drive lifecycle, and syncing the
    state bidirectionally with the connected phone.  The tool list
    (``tools.json``) is the single source of truth for what is enabled — the
    Settings screen now only owns the autostart flag.

    Signals:
        tools_loaded (Signal[list]): The full ``list[ToolDTO]`` for the grid.
        tools_changed (Signal[object]): Emitted alongside ``tools_loaded`` for
            subscribers that only need a change notification (e.g. a count badge).
        tool_enabled_changed (Signal[str, bool]): A single tool's enabled state
            changed ``(title, enabled)`` — lets the grid update one card's toggle
            without rebuilding the whole grid.
    """

    tools_loaded: Signal = Signal(list)
    tools_changed: Signal = Signal(object)
    tool_enabled_changed: Signal = Signal(str, bool)

    def __init__(
            self,
            tool_service: ToolService,
            clipboard_service: ClipboardService,
            webcam_service: WebcamService,
            backup_service: BackupService,
            virtual_drive_service: VirtualDriveService,
            connectivity_service: ConnectivityService,
            device_viewmodel: DeviceViewModel,
            settings_service: SettingsService,
            parent: QObject | None = None,
    ) -> None:
        """Wire the feature services and load the tool list.

        Args:
            tool_service: Source of truth for the tool list (tools.json).
            clipboard_service: Gated by the "Clipboard Sync" tool.
            webcam_service: Gated by the "Webcam" tool.
            backup_service: Gated by the "Backup" tool.
            virtual_drive_service: Lifecycle-managed by the "Virtual Drive" tool.
            connectivity_service: Used to start/stop Virtual Drive immediately
                when toggled while a device is connected.
            device_viewmodel: Provides the connect/disconnect signals the
                Virtual Drive lifecycle binds to.
            settings_service: Owns the TauSync tool-state sync with the phone.
            parent: Optional parent QObject.
        """
        super().__init__(parent)

        self._tool_service: ToolService = tool_service
        self._clipboard: ClipboardService = clipboard_service
        self._webcam: WebcamService = webcam_service
        self._backup: BackupService = backup_service
        self._vdrive: VirtualDriveService = virtual_drive_service
        self._connectivity: ConnectivityService = connectivity_service
        self._device_vm: DeviceViewModel = device_viewmodel
        self._settings: SettingsService = settings_service

        self._tools: list[ToolDTO] = []
        self._vdrive_wired: bool = False

        # Apply the persisted enabled state to the feature services up-front
        # (mirrors the old SettingsViewModel construction behaviour).
        self._apply_initial_state()

        # Last feature state the phone has agreed to ("approved cross-platform
        # value").  A user toggle is applied optimistically and pushed; if that
        # push times out or errors the state is rolled back to this baseline.
        # The persisted state is treated as the agreed baseline at startup.
        self._last_approved: dict[str, bool] = {
            title: self._feature_enabled(title) for title in FEATURE_TITLES
        }

        # Phone → PC: apply pushed feature states without echoing back. These are
        # queued cross-thread connections (emitted from TauSync daemon threads).
        self._settings.tools_state_received.connect(self._apply_virtual_drive_from_phone)
        self._settings.clipboard_state_received.connect(self._apply_clipboard_from_phone)
        self._settings.webcam_state_received.connect(self._apply_webcam_from_phone)
        self._settings.backup_state_received.connect(self._apply_backup_from_phone)

        # Push outcome (also queued from a TauSync daemon thread): success advances
        # the approved baseline, failure rolls the tool state back to it.
        self._settings.tools_push_succeeded.connect(self._on_push_succeeded)
        self._settings.tools_push_failed.connect(self._on_push_failed)

        # Populate the in-memory DTO cache for the grid.  The tool store is
        # in-memory (JSON-backed), so this is a cheap synchronous read.
        self._reload()

    # ── DTO conversion ──────────────────────────────────────────────────────────

    @staticmethod
    def _to_dto(entity: ToolEntity) -> ToolDTO:
        # Map an entity to the flat DTO the view layer consumes.
        return ToolDTO(entity.title, entity.description, entity.icon_path, entity.is_enabled)

    # ── Grid population ─────────────────────────────────────────────────────────

    def _reload(self) -> None:
        # Refresh the in-memory DTO cache from the tool store.
        self._tools = [self._to_dto(t) for t in self._tool_service.get_all()]

    def load_tools(self) -> None:
        """Refresh from the store and emit the tool list to the grid.

        Called on construction and whenever the dashboard is shown.

        Emits:
            tools_loaded / tools_changed: With the current ``list[ToolDTO]``.
        """
        self._reload()
        self.tools_loaded.emit(self._tools)
        self.tools_changed.emit(self._tools)

    def feature_tools(self) -> list[ToolDTO]:
        """Return the four feature tools (in catalog order) for the Settings page.

        Excludes the "Send File to Phone" action tool. The Settings screen uses
        this to build one on/off row per feature.

        Returns:
            The feature ``ToolDTO`` objects currently known to the viewmodel.
        """
        by_title = {dto.title: dto for dto in self._tools}
        return [by_title[title] for title in FEATURE_TITLES if title in by_title]

    # ── User-initiated toggle (from the Settings page) ──────────────────────────

    @Slot(str, bool)
    def set_tool_enabled(self, title: str, enabled: bool) -> None:
        """Enable/disable a tool, apply its side effect, and sync the phone.

        Args:
            title: The tool's title (primary key).
            enabled: The new enabled state.
        """
        if not self._persist_enabled(title, enabled):
            return
        # User-initiated change → push the full feature state to the phone.
        self._push_feature_state()

    # ── Phone-initiated apply (phone → PC, never echoed back) ────────────────────
    # A phone-pushed value is agreed cross-platform, so it also advances the
    # approved baseline — otherwise a later failed PC push could roll the phone's
    # own value back.

    @Slot(bool)
    def _apply_virtual_drive_from_phone(self, value: bool) -> None:
        self._persist_enabled(TITLE_VIRTUAL_DRIVE, value)
        self._last_approved[TITLE_VIRTUAL_DRIVE] = value

    @Slot(bool)
    def _apply_clipboard_from_phone(self, value: bool) -> None:
        self._persist_enabled(TITLE_CLIPBOARD, value)
        self._last_approved[TITLE_CLIPBOARD] = value

    @Slot(bool)
    def _apply_webcam_from_phone(self, value: bool) -> None:
        self._persist_enabled(TITLE_WEBCAM, value)
        self._last_approved[TITLE_WEBCAM] = value

    @Slot(bool)
    def _apply_backup_from_phone(self, value: bool) -> None:
        self._persist_enabled(TITLE_BACKUP, value)
        self._last_approved[TITLE_BACKUP] = value

    # ── Push outcome (PC → phone result) ─────────────────────────────────────────

    @Slot(bool, bool, bool, bool)
    def _on_push_succeeded(
        self,
        virtual_drive: bool,
        clipboard: bool,
        webcam: bool,
        backup: bool,
    ) -> None:
        # The phone accepted this state — make it the new approved baseline.
        self._last_approved = {
            TITLE_VIRTUAL_DRIVE: virtual_drive,
            TITLE_CLIPBOARD: clipboard,
            TITLE_WEBCAM: webcam,
            TITLE_BACKUP: backup,
        }

    @Slot()
    def _on_push_failed(self) -> None:
        # Push timed out / errored — roll every feature tool back to the last
        # state the phone agreed to.  _persist_enabled no-ops unchanged tools and,
        # for the reverted one, undoes the service side effect and re-emits
        # tool_enabled_changed so the switch flips back silently.  It does not
        # re-push, so there is no feedback loop.
        for title, value in self._last_approved.items():
            self._persist_enabled(title, value)

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _persist_enabled(self, title: str, enabled: bool) -> bool:
        # Persist the new enabled state, apply the feature side effect, and
        # notify the grid.  Returns False (a no-op) when the value is unchanged
        # so callers can skip any follow-up work (e.g. a phone push).
        entity = self._tool_service.get_by_id(title)
        if entity is None or entity.is_enabled == enabled:
            return False
        self._tool_service.save_tool(replace(entity, is_enabled=enabled))
        self._apply_feature(title, enabled)
        self._update_cache(title, enabled)
        self.tool_enabled_changed.emit(title, enabled)
        return True

    def _apply_feature(self, title: str, enabled: bool) -> None:
        # Apply a feature tool's enabled state to its background service.
        if title == TITLE_CLIPBOARD:
            self._clipboard.set_enabled(enabled)
        elif title == TITLE_WEBCAM:
            self._webcam.set_enabled(enabled)
        elif title == TITLE_BACKUP:
            self._backup.set_enabled(enabled)
        elif title == TITLE_VIRTUAL_DRIVE:
            if enabled:
                self._wire_virtual_drive()
            else:
                self._unwire_virtual_drive()

    def _apply_initial_state(self) -> None:
        # Push persisted feature states into the services at startup.
        for tool in self._tool_service.get_all():
            if tool.title == TITLE_CLIPBOARD:
                self._clipboard.set_enabled(tool.is_enabled)
            elif tool.title == TITLE_WEBCAM:
                self._webcam.set_enabled(tool.is_enabled)
            elif tool.title == TITLE_BACKUP:
                self._backup.set_enabled(tool.is_enabled)
            elif tool.title == TITLE_VIRTUAL_DRIVE and tool.is_enabled:
                self._wire_virtual_drive()

    def _update_cache(self, title: str, enabled: bool) -> None:
        # Keep the cached DTO list coherent so a later load_tools() is accurate.
        for i, dto in enumerate(self._tools):
            if dto.title == title:
                self._tools[i] = replace(dto, is_enabled=enabled)
                break

    def _feature_enabled(self, title: str) -> bool:
        entity = self._tool_service.get_by_id(title)
        return bool(entity and entity.is_enabled)

    def _push_feature_state(self) -> None:
        # Push all four feature flags so the phone always has a full picture.
        self._settings.push_tools_state(
            self._feature_enabled(TITLE_VIRTUAL_DRIVE),
            self._feature_enabled(TITLE_CLIPBOARD),
            self._feature_enabled(TITLE_WEBCAM),
            self._feature_enabled(TITLE_BACKUP),
        )

    # ── Virtual Drive lifecycle (moved from SettingsViewModel) ──────────────────

    def _wire_virtual_drive(self) -> None:
        # Connect device connect/disconnect to the VirtualDrive lifecycle.
        if self._vdrive_wired:
            return
        self._device_vm.device_connected.connect(self._vdrive.start)
        self._device_vm.device_disconnected.connect(self._vdrive.stop)
        self._vdrive_wired = True
        # Mount immediately if a device is already connected — device_connected is
        # a one-shot transition signal and won't re-fire for the existing session.
        if self._connectivity.connected:
            self._vdrive.start()

    def _unwire_virtual_drive(self) -> None:
        # Disconnect lifecycle signals and stop the service if connected now.
        if self._vdrive_wired:
            try:
                self._device_vm.device_connected.disconnect(self._vdrive.start)
                self._device_vm.device_disconnected.disconnect(self._vdrive.stop)
            except RuntimeError:
                pass  # Signal was never connected — safe to ignore.
            self._vdrive_wired = False
        if self._connectivity.connected:
            self._vdrive.stop()

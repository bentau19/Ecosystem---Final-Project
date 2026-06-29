import json
import threading

from PySide6.QtCore import QObject, Signal

from domain.dto.settings import SettingsDTO
from domain.enums.settings_channels import SettingsChannels
from repositories.settings import SettingsRepository
from services.connectivity import ConnectivityService


# JSON keys used on the wire by both sides for each tool toggle.
# Matches the Android payload (camelCase) — see SettingsUseCase.pushToolsState
# and SettingsChannelHandler on the Android side.
_WIRE_KEY_VIRTUAL_DRIVE: str = "virtualDrive"
_WIRE_KEY_CLIPBOARD: str = "clipboard"
_WIRE_KEY_WEBCAM: str = "webcam"
_WIRE_KEY_BACKUP: str = "backup"
_WIRE_KEY_DARK_MODE: str = "darkMode"

# How long the PC waits for the phone to meet on the push channel before the
# handshake is declared timed out.  Kept short (vs. TauSync's 60 s default) so
# a failed push reverts the toggle quickly enough to feel responsive.
_PUSH_TIMEOUT_SECONDS: int = 10


class SettingsService(QObject):
    """Service layer over :class:`~repositories.settings.SettingsRepository`.

    Enforces the architectural rule that ViewModels must not import from the
    repositories layer directly.  Local settings I/O is synchronous and fast
    (a small JSON file), so no background executor is needed for ``load`` /
    ``save``.

    Also owns the TauSync sync of the tool-enabled state with the connected
    phone (Virtual Drive, Clipboard, and Webcam).  All network I/O runs on
    daemon background threads — never a ``QThread`` — because TauSync makes
    blocking .NET calls via pythonnet.  ``connectivity.tau`` is read per-call
    so reconnects are handled transparently.

    Signals:
        tools_state_received (Signal[bool]): Emitted with the phone's Virtual
            Drive enabled state after it pushes ``settings_tools_android_to_pc``.
            Connect to a main-thread slot that applies the value without echoing
            it back to the phone.
        clipboard_state_received (Signal[bool]): Emitted with the phone's
            clipboard-sync enabled state.
        webcam_state_received (Signal[bool]): Emitted with the phone's webcam
            enabled state.
        backup_state_received (Signal[bool]): Emitted with the phone's backup
            enabled state.
        tools_push_succeeded (Signal[bool, bool, bool, bool]): Emitted after a
            push to the phone completes, carrying the four values the phone
            accepted ``(virtual_drive, clipboard, webcam, backup)``.  Lets the
            viewmodel advance its "last approved" baseline.
        tools_push_failed (Signal): Emitted when a push errors or times out, so
            the viewmodel can roll the tool state back to the last value the
            phone agreed to.
    """

    tools_state_received: Signal = Signal(bool)
    clipboard_state_received: Signal = Signal(bool)
    webcam_state_received: Signal = Signal(bool)
    backup_state_received: Signal = Signal(bool)
    dark_mode_received: Signal = Signal(bool)
    tools_push_succeeded: Signal = Signal(bool, bool, bool, bool)
    tools_push_failed: Signal = Signal()

    def __init__(
        self,
        repository: SettingsRepository,
        connectivity: ConnectivityService,
        parent: QObject | None = None,
    ) -> None:
        """Wrap the settings repository and connectivity service.

        Args:
            repository: The persistence layer instance from the DI root.
            connectivity: Application-level connectivity service; ``tau`` is
                accessed per-call so reconnects are handled transparently.
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._repository: SettingsRepository = repository
        self._connectivity: ConnectivityService = connectivity
        self._threads_lock: threading.Lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    # ── Local persistence ───────────────────────────────────────────────────────

    def load(self) -> SettingsDTO:
        """Read and return the persisted settings, falling back to defaults.

        Returns:
            A :class:`~domain.dto.settings.SettingsDTO` populated from disk.
        """
        return self._repository.load()

    def save(self, settings: SettingsDTO) -> None:
        """Persist *settings* to disk.

        Args:
            settings: The updated :class:`~domain.dto.settings.SettingsDTO` to save.
        """
        self._repository.save(settings)

    # ── Tool-enabled state sync ──────────────────────────────────────────────────

    def receive_tools_state(self) -> None:
        """Read the phone's tool-enabled state on a daemon thread.

        Registered in :attr:`~services.phone_request.PhoneRequestService.operations`
        under :attr:`SettingsChannels.TOOLS_ANDROID_TO_PC`; invoked by the poll
        loop when the phone is waiting on that channel.  Spawns a daemon thread
        so the poll loop is never blocked.
        """
        t = threading.Thread(target=self._receive_tools_state, daemon=True)
        with self._threads_lock:
            self._threads.append(t)
        t.start()

    def push_tools_state(
        self,
        virtual_drive_enabled: bool,
        clipboard_enabled: bool,
        webcam_enabled: bool,
        backup_enabled: bool,
    ) -> None:
        """Push the PC's tool-enabled state to the phone.

        Sends all four tool flags in a single JSON payload so the phone always
        has a complete picture.  No-op when no device is connected.  Spawns a
        daemon thread so the caller (the GUI thread) is never blocked by TauSync
        network I/O.

        Args:
            virtual_drive_enabled: Current Virtual Drive enabled state.
            clipboard_enabled: Current clipboard-sync enabled state.
            webcam_enabled: Current webcam mirroring enabled state.
            backup_enabled: Current backup enabled state.
        """
        if not self._connectivity.connected:
            return
        t = threading.Thread(
            target=self._push_tools_state,
            args=(virtual_drive_enabled, clipboard_enabled, webcam_enabled, backup_enabled),
            daemon=True,
        )
        with self._threads_lock:
            self._threads.append(t)
        t.start()

    def push_dark_mode(self, dark: bool) -> None:
        """Push only the dark mode flag to the phone.

        Sends ``{"darkMode": <value>}`` on ``TOOLS_PC_TO_ANDROID``.  The phone
        uses ``optBoolean`` with its current persisted value as default, so all
        other tool flags are unaffected.  No-op when not connected.

        Args:
            dark: ``True`` to push dark mode on, ``False`` for light mode.
        """
        if not self._connectivity.connected:
            return
        t = threading.Thread(
            target=self._push_dark_mode,
            args=(dark,),
            daemon=True,
        )
        with self._threads_lock:
            self._threads.append(t)
        t.start()

    # ── Private ──────────────────────────────────────────────────────────────────

    def _receive_tools_state(self) -> None:
        # Background worker: connect, read JSON, emit a signal per field present.
        # Absent fields are silently skipped (forward-compatible with older phone
        # builds that don't yet send all four keys).
        try:
            tau = self._connectivity.tau
            with tau.connect(SettingsChannels.TOOLS_ANDROID_TO_PC.value) as stream:
                raw = stream.read_all().decode("utf-8")

            payload: dict = json.loads(raw)

            if _WIRE_KEY_VIRTUAL_DRIVE in payload:
                self.tools_state_received.emit(bool(payload[_WIRE_KEY_VIRTUAL_DRIVE]))
            if _WIRE_KEY_CLIPBOARD in payload:
                self.clipboard_state_received.emit(bool(payload[_WIRE_KEY_CLIPBOARD]))
            if _WIRE_KEY_WEBCAM in payload:
                self.webcam_state_received.emit(bool(payload[_WIRE_KEY_WEBCAM]))
            if _WIRE_KEY_BACKUP in payload:
                self.backup_state_received.emit(bool(payload[_WIRE_KEY_BACKUP]))
            if _WIRE_KEY_DARK_MODE in payload:
                self.dark_mode_received.emit(bool(payload[_WIRE_KEY_DARK_MODE]))

        except Exception as exc:
            print(f"[SettingsService] Error receiving tool state: {exc}")

    def _push_tools_state(
        self,
        virtual_drive_enabled: bool,
        clipboard_enabled: bool,
        webcam_enabled: bool,
        backup_enabled: bool,
    ) -> None:
        # Background worker: connect, write JSON payload with all four fields, close channel.
        # On success the phone has the new state — emit tools_push_succeeded so the
        # viewmodel can advance its baseline.  On any failure (most importantly a
        # handshake timeout) emit tools_push_failed so it can revert the toggle.
        try:
            payload = json.dumps({
                _WIRE_KEY_VIRTUAL_DRIVE: virtual_drive_enabled,
                _WIRE_KEY_CLIPBOARD: clipboard_enabled,
                _WIRE_KEY_WEBCAM: webcam_enabled,
                _WIRE_KEY_BACKUP: backup_enabled,
            })
            tau = self._connectivity.tau
            with tau.connect(
                SettingsChannels.TOOLS_PC_TO_ANDROID.value,
                timeout_seconds=_PUSH_TIMEOUT_SECONDS,
            ) as stream:
                stream.write_string(payload)
        except Exception as exc:
            print(f"[SettingsService] Error pushing tool state to phone: {exc}")
            self.tools_push_failed.emit()
            return
        self.tools_push_succeeded.emit(
            virtual_drive_enabled, clipboard_enabled, webcam_enabled, backup_enabled
        )

    def _push_dark_mode(self, dark: bool) -> None:
        # Background worker: write only {"darkMode": <value>} so the phone updates its
        # theme without touching the other tool flags (phone keeps them via optBoolean).
        try:
            payload = json.dumps({_WIRE_KEY_DARK_MODE: dark})
            tau = self._connectivity.tau
            with tau.connect(
                SettingsChannels.TOOLS_PC_TO_ANDROID.value,
                timeout_seconds=_PUSH_TIMEOUT_SECONDS,
            ) as stream:
                stream.write_string(payload)
        except Exception as exc:
            print(f"[SettingsService] Error pushing dark mode to phone: {exc}")

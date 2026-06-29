import sys
from typing import Final

from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtGui import QGuiApplication


def _read_registry_dark_mode() -> bool | None:
    # Qt's colorScheme() returns wrong values on some Windows configs (known Qt bug),
    # so the registry is the authoritative source on Windows.
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            # 0 → dark mode active, 1 → light mode active
            return value == 0
    except OSError:
        return None


def _detect_is_dark() -> bool:
    # Prefer the registry value on Windows; fall back to Qt style hints on other platforms.
    registry_result = _read_registry_dark_mode()
    if registry_result is not None:
        return registry_result

    # Non-Windows fallback via Qt style hints
    scheme = QGuiApplication.styleHints().colorScheme()
    return scheme != Qt.ColorScheme.Light


class ThemeManager(QObject):
    """Singleton that tracks the Windows system dark/light color scheme.

    Reads the current scheme via the Windows registry at construction time
    (most reliable) and re-emits :attr:`theme_changed` whenever the user
    switches the system preference while the app is running.

    An in-app override set via :meth:`force` takes precedence over the system
    value until the app is restarted or :meth:`force` is called again.

    Usage::

        from app.theme_manager import theme_manager

        theme_manager.theme_changed.connect(self._setup_style)
        is_dark = theme_manager.is_dark
    """

    #: Emitted (with no arguments) whenever the system flips dark ↔ light.
    theme_changed: Signal = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._is_dark: bool = _detect_is_dark()
        self._override: bool | None = None
        # Qt's colorSchemeChanged fires even when colorScheme() reads wrong initially
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_scheme_changed)

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def is_dark(self) -> bool:
        """``True`` when dark mode is active (override takes precedence over system)."""
        if self._override is not None:
            return self._override
        return self._is_dark

    def force(self, dark: bool) -> None:
        """Override the system theme with an explicit in-app value.

        Emits :attr:`theme_changed` if the effective ``is_dark`` value changes.

        Args:
            dark: ``True`` to force dark mode, ``False`` to force light mode.
        """
        if self._override == dark:
            return
        self._override = dark
        self.theme_changed.emit()

    # ── Private slots ──────────────────────────────────────────────────────────

    @Slot(Qt.ColorScheme)
    def _on_scheme_changed(self, scheme: Qt.ColorScheme) -> None:
        # When an override is active, system changes don't affect is_dark.
        if self._override is not None:
            return
        # Re-read the authoritative source; skip emit if nothing actually changed.
        new_is_dark = _detect_is_dark()
        if new_is_dark == self._is_dark:
            return  # no real change — guard against spurious signals
        self._is_dark = new_is_dark
        self.theme_changed.emit()


#: Module-level singleton — import this everywhere, never instantiate directly.
theme_manager: Final[ThemeManager] = ThemeManager()

import logging
import os
import subprocess
import webbrowser
import winreg
from pathlib import Path
from typing import Final

from PySide6.QtCore import QObject

from domain.dto.dependency_info import DependencyInfoDTO
from domain.enums.dependency import Dependency

logger = logging.getLogger(__name__)

# Bundled OBS installer locations written by the MSI into the install dir.
_BUNDLED_OBS_INSTALLERS: Final[tuple[Path, ...]] = (
    Path(r"C:\Program Files\SyncDose\dependencies\OBS-Studio-32.1.2-Windows-x64-Installer.exe"),
    Path(r"C:\Program Files (x86)\SyncDose\dependencies\OBS-Studio-32.1.2-Windows-x64-Installer.exe"),
)

# Public download pages opened when no bundled installer is available.
_DOWNLOAD_PAGES: Final[dict[Dependency, str]] = {
    Dependency.DOTNET8: "https://dotnet.microsoft.com/download/dotnet/8.0",
    Dependency.WINFSP: "https://github.com/winfsp/winfsp/releases",
    Dependency.OBS: "https://obsproject.com/download",
}

# Static display metadata per dependency: (display_name, description, required).
_METADATA: Final[dict[Dependency, tuple[str, str, bool]]] = {
    Dependency.DOTNET8: (
        ".NET 8 Runtime",
        "Required for internal system connectivity.",
        True,
    ),
    Dependency.WINFSP: (
        "WinFSP",
        "Required for the virtual drive mounting feature.",
        False,
    ),
    Dependency.OBS: (
        "OBS Studio",
        "Required for phone camera streaming.",
        False,
    ),
}


class DependencyService(QObject):
    """Detects required Windows components and routes install actions.

    Owns both halves of dependency handling that previously lived as loose
    free functions in ``app/obs_checker.py`` and as decision logic inside the
    view:

    * **Detection** — :meth:`check_missing` probes the registry / filesystem
      for .NET 8, WinFSP and OBS Studio and returns a ``list[DependencyInfoDTO]``
      describing whatever is absent.
    * **Install** — :meth:`install` opens the correct download page (or runs
      the bundled OBS installer) for a single component.

    Detection is synchronous and carries no TauSync / pythonnet dependency, so
    it can run in the ``main.py`` bootstrap *before* the .NET-loading import
    chain — gating startup when a required component is missing.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the service.

        Args:
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)

    # ── Detection ──────────────────────────────────────────────────────────────

    def check_missing(self) -> list[DependencyInfoDTO]:
        """Return a DTO for each required component that is not installed.

        Returns:
            A ``list[DependencyInfoDTO]`` — empty when every dependency is
            present. Ordered .NET 8 → WinFSP → OBS so required components
            surface first.
        """
        installed: dict[Dependency, bool] = {
            Dependency.DOTNET8: self._is_dotnet8_installed(),
            Dependency.WINFSP: self._is_winfsp_installed(),
            Dependency.OBS: self._is_obs_installed(),
        }
        return [
            self._build_dto(dependency)
            for dependency, is_installed in installed.items()
            if not is_installed
        ]

    # ── Install actions ─────────────────────────────────────────────────────────

    def install(self, dependency: Dependency) -> None:
        """Kick off installation of a single *dependency*.

        For OBS a bundled installer (shipped by the MSI) is run silently when
        present; otherwise the public download page is opened. .NET 8 and WinFSP
        always open their download pages.

        Args:
            dependency: The component the user chose to install.
        """
        if dependency is Dependency.OBS and self._try_run_bundled_obs():
            return
        self._open_download_page(dependency)

    # ── DTO assembly ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_dto(dependency: Dependency) -> DependencyInfoDTO:
        # Wrap the dependency's static display metadata in a view-facing DTO.
        display_name, description, required = _METADATA[dependency]
        return DependencyInfoDTO(
            dependency=dependency,
            display_name=display_name,
            description=description,
            required=required,
        )

    # ── .NET 8 detection ────────────────────────────────────────────────────────

    def _is_dotnet8_installed(self) -> bool:
        # Probe every known dotnet root for the .NET 8 shared framework.
        # Inspecting the shared-framework folder is more reliable than the
        # registry, whose layout varies between installer builds.
        for root in self._dotnet_roots():
            framework_dir = root / "shared" / "Microsoft.NETCore.App"
            if not framework_dir.is_dir():
                continue
            for version_dir in framework_dir.glob("8.0.*"):
                if (version_dir / "System.Private.CoreLib.dll").exists():
                    logger.info("Found .NET 8 at %s", version_dir)
                    return True
        # Fall back to the CLI for custom install paths the probe above misses.
        return self._dotnet_cli_reports_runtime8()

    @staticmethod
    def _dotnet_roots() -> list[Path]:
        # Candidate dotnet install roots: DOTNET_ROOT override + standard dirs.
        roots: list[Path] = []
        env_root = os.environ.get("DOTNET_ROOT")
        if env_root:
            roots.append(Path(env_root))
        roots.append(Path(r"C:\Program Files\dotnet"))
        roots.append(Path(r"C:\Program Files (x86)\dotnet"))
        return roots

    @staticmethod
    def _dotnet_cli_reports_runtime8() -> bool:
        # Ask the dotnet CLI for installed runtimes and look for a .NET 8 entry.
        # A missing dotnet on PATH (i.e. nothing installed) raises OSError → False.
        try:
            result = subprocess.run(
                ["dotnet", "--list-runtimes"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError) as e:
            logger.debug("dotnet CLI runtime probe failed: %s", e)
            return False
        return any(
            line.startswith("Microsoft.NETCore.App 8.")
            for line in result.stdout.splitlines()
        )

    # ── WinFSP detection ──────────────────────────────────────────────────────

    def _is_winfsp_installed(self) -> bool:
        # WinFSP records its install under HKLM\SOFTWARE\WinFsp (registered in
        # the 32-bit view). Probing both registry views directly is faster and
        # more reliable than enumerating every Uninstall subkey.
        return self._registry_key_exists(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WinFsp"
        )

    # ── OBS Studio detection ────────────────────────────────────────────────────

    def _is_obs_installed(self) -> bool:
        # OBS registers an "OBS Studio" Uninstall entry. Check HKLM (both
        # registry views) and the per-user HKCU hive so machine- and user-scope
        # installs are both detected.
        sub_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\OBS Studio"
        return (
            self._registry_key_exists(winreg.HKEY_LOCAL_MACHINE, sub_key)
            or self._registry_key_exists(winreg.HKEY_CURRENT_USER, sub_key)
        )

    @staticmethod
    def _registry_key_exists(root: int, sub_key: str) -> bool:
        # True when sub_key opens under root in either the 64- or 32-bit view.
        for view_flag in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(root, sub_key, 0, winreg.KEY_READ | view_flag):
                    return True
            except FileNotFoundError:
                continue
            except OSError as e:
                logger.warning("Registry probe failed for %s: %s", sub_key, e)
        return False

    # ── Install helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _try_run_bundled_obs() -> bool:
        # Run the MSI-bundled OBS installer silently if one is present on disk.
        for installer in _BUNDLED_OBS_INSTALLERS:
            if not installer.exists():
                continue
            try:
                logger.info("Running bundled OBS installer at %s", installer)
                subprocess.Popen(
                    [str(installer), "/S", r"/D=C:\Program Files\obs-studio"],
                    shell=False,
                )
                return True
            except OSError as e:
                logger.error("Failed to run bundled OBS installer: %s", e)
                return False
        logger.info("No bundled OBS installer found")
        return False

    @staticmethod
    def _open_download_page(dependency: Dependency) -> None:
        # Open the dependency's public download page in the default browser.
        url = _DOWNLOAD_PAGES[dependency]
        try:
            webbrowser.open(url)
        except Exception as e:
            logger.error("Failed to open download page %s: %s", url, e)

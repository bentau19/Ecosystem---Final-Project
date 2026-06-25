"""
Dependency checker for required Windows components.

Detects if OBS Studio, .NET 8, and WinFSP are installed. Provides utilities
to reinstall them if missing:
- OBS Studio: required for phone camera streaming via Virtual Camera
- .NET 8: required by TauSync (pythonnet CLR bridge)
- WinFSP: required for Virtual Drive feature
"""

import logging
import subprocess
import winreg
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def is_obs_installed() -> bool:
    """
    Check if OBS Studio is installed by looking for its registry entry.

    Returns:
        True if OBS Studio is found in registry, False otherwise.
    """
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\OBS Studio",
            access=winreg.KEY_READ,
        ):
            return True
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.warning(f"Error checking OBS installation: {e}")
        return False


def get_obs_install_path() -> Optional[Path]:
    """
    Get the OBS Studio installation directory from registry.

    Returns:
        Path to OBS installation if found, None otherwise.
    """
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\OBS Studio",
            access=winreg.KEY_READ,
        ) as key:
            install_location, _ = winreg.QueryValueEx(key, "InstallLocation")
            if install_location:
                return Path(install_location)
    except (FileNotFoundError, OSError) as e:
        logger.warning(f"Could not retrieve OBS install path: {e}")
    return None


def try_reinstall_obs_from_bundled() -> bool:
    """
    Attempt to reinstall OBS from a bundled installer if available.

    Looks for OBS installer in:
    1. Program Files\SyncDose\dependencies\
    2. Temp folder (if CI downloaded it)

    Returns:
        True if installer found and executed, False otherwise.
    """
    possible_paths = [
        Path("C:\\Program Files\\SyncDose\\dependencies\\OBS-Studio-32.1.2-Windows-x64-Installer.exe"),
        Path("C:\\Program Files (x86)\\SyncDose\\dependencies\\OBS-Studio-32.1.2-Windows-x64-Installer.exe"),
    ]

    for installer_path in possible_paths:
        if installer_path.exists():
            try:
                logger.info(f"Found bundled OBS installer at {installer_path}, running...")
                subprocess.Popen(
                    [str(installer_path), "/S", "/D=C:\\Program Files\\obs-studio"],
                    shell=False,
                )
                return True
            except Exception as e:
                logger.error(f"Failed to run OBS installer: {e}")
                return False

    logger.warning("No bundled OBS installer found")
    return False


def open_obs_download_page() -> None:
    """Open the OBS Studio download page in the default browser."""
    import webbrowser

    try:
        webbrowser.open("https://obsproject.com/download")
    except Exception as e:
        logger.error(f"Failed to open browser: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# .NET 8 Runtime Check
# ─────────────────────────────────────────────────────────────────────────────


def is_dotnet8_installed() -> bool:
    """
    Check if .NET 8 runtime is installed by looking for the shared framework folder.

    This is more reliable than registry checking since .NET uses different registry
    paths depending on installer build.

    Returns:
        True if .NET 8.0.16 shared framework is found, False otherwise.
    """
    dotnet_path = Path(r"C:\Program Files\dotnet\shared\Microsoft.NETCore.App\8.0.16\System.Private.CoreLib.dll")
    if dotnet_path.exists():
        return True

    # Also check other common .NET 8 versions in case user has a newer patch
    dotnet_dir = Path(r"C:\Program Files\dotnet\shared\Microsoft.NETCore.App")
    if dotnet_dir.exists():
        for version_dir in dotnet_dir.glob("8.0.*"):
            if (version_dir / "System.Private.CoreLib.dll").exists():
                logger.info(f"Found .NET 8 at {version_dir}")
                return True

    return False


def open_dotnet_download_page() -> None:
    """Open the .NET 8 download page in the default browser."""
    import webbrowser

    try:
        webbrowser.open("https://dotnet.microsoft.com/download/dotnet/8.0")
    except Exception as e:
        logger.error(f"Failed to open browser: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# WinFSP Check
# ─────────────────────────────────────────────────────────────────────────────


def is_winfsp_installed() -> bool:
    """
    Check if WinFSP is installed by looking for its registry entry.

    Returns:
        True if WinFSP is found in registry, False otherwise.
    """
    try:
        # WinFSP registers itself in the Uninstall key
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            access=winreg.KEY_READ,
        ) as uninstall_key:
            # Try to open WinFSP's subkey (it's registered with a GUID)
            try:
                # Check by DisplayName instead since we don't know the exact GUID
                for i in range(winreg.QueryInfoKey(uninstall_key)[0]):
                    subkey_name = winreg.EnumKey(uninstall_key, i)
                    try:
                        with winreg.OpenKey(uninstall_key, subkey_name) as subkey:
                            display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                            if "WinFSP" in display_name:
                                return True
                    except (FileNotFoundError, OSError):
                        continue
            except Exception as e:
                logger.warning(f"Error enumerating Uninstall key: {e}")

    except Exception as e:
        logger.warning(f"Error checking WinFSP installation: {e}")

    return False


def open_winfsp_download_page() -> None:
    """Open the WinFSP download page in the default browser."""
    import webbrowser

    try:
        webbrowser.open("https://github.com/winfsp/winfsp/releases")
    except Exception as e:
        logger.error(f"Failed to open browser: {e}")

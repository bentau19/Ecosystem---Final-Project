# SyncDose — Windows Client

A desktop dashboard application for monitoring and managing connected Android devices on Windows.
Built with Python 3.13 and PySide6, SyncDose provides a real-time view of device status,
bidirectional file transfer via Windows shell integration, and a configurable tools grid.

---

## Table of Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Prerequisites](#prerequisites)
4. [Development Setup](#development-setup)
5. [Running the App](#running-the-app)
6. [Running Tests](#running-tests)
7. [Production Build](#production-build)
8. [Project Structure](#project-structure)
9. [Architecture](#architecture)
10. [DI Root — AppState](#di-root--appstate)
11. [Layer Boundaries](#layer-boundaries)
12. [Threading Rules](#threading-rules)
13. [Screen Navigation](#screen-navigation)
14. [Theming System](#theming-system)
15. [Design Tokens](#design-tokens)
16. [Services](#services)
    - [ConnectivityService](#connectivityservice)
    - [DeviceInfoService](#deviceinfoservice)
    - [FileTransferService](#filetransferservice)
    - [BackupService](#backupservice)
    - [VirtualDriveService](#virtualdriveservice)
    - [PhoneRequestService](#phonerequestservice)
    - [ToolService](#toolservice)
17. [ViewModels](#viewmodels)
18. [Repositories](#repositories)
19. [Serializers](#serializers)
20. [Database](#database)
21. [File Transfer & IPC](#file-transfer--ipc)
22. [Qt Resources](#qt-resources)

---

## Features

- **Device Dashboard** — Battery level, charging status, storage usage, OS info, and device
  name in real time
- **Login Screen** — QR code pairing panel (displays local IP) + scrollable list of previously
  connected devices with one-click reconnect cards
- **File Transfer** — Send files to the phone from the dashboard; receive files from the phone
  with an accept/reject toast prompt. Also integrates with the Windows "Send with SyncDose"
  shell context menu via a named pipe between two executables
- **Tools Grid** — Configurable grid of action tiles backed by SQLite, with enabled/disabled
  per-tool state
- **Dark / Light Theme** — Tracks the Windows system color scheme (via the registry) and
  re-themes all widgets dynamically without a restart
- **System Tray** — Minimize-to-tray on close; restore via double-click or right-click menu
- **Virtual Drive** — Mounts the connected phone as a Windows drive letter using WinFSP.
  `VirtualDrive.exe` forwards every Explorer filesystem operation (`list`, `stat`, `read`,
  `write`, `create`, `delete`, `rename`) to Android via TauSync, so the phone's storage
  appears and behaves like a local disk
- **Sidebar Navigation** — Icon-based sidebar with logo; `NavigationManager` drives all
  screen transitions without coupling widgets to `MainWindow`
- **Clipboard Sync** — Two-directional clipboard sync over TauSync. Android → PC: user taps
  "Send Clipboard to PC"; PC → Android: automatic push on every local clipboard change.
  SHA-256 hash guard prevents echo loops in both directions
- **Camera Mirror** — Receives a live JPEG frame stream from the Android app and feeds it
  into a virtual webcam via `pyvirtualcam` + OBS Virtual Camera driver. Portrait frames are
  pillarboxed to preserve aspect ratio. Requires OBS Virtual Camera to be installed on the PC

---

## Requirements

| Dependency        | Version    | Source                              | Notes |
|-------------------|------------|-------------------------------------|-------|
| Python            | 3.13       | system                              | f-strings, `match`, and type-union syntax (`A \| B`) are used |
| PySide6           | ≥ 6.11.1   | `requirements.txt`                  | Qt bindings |
| pythonnet         | ≥ 3.0.0    | `TauSync/windows/requirements.txt`  | CLR bridge for TauSync .NET calls — installed in setup step 5 |
| tausync_py        | local pkg   | `pip install ../TauSync/windows`    | TauSync Python wrapper — requires the `.dll` (see setup) |
| qrcode[pil]       | ≥ 7.4.2    | `requirements.txt`                  | QR image generation for the login panel |
| xxhash            | ≥ 3.7.0    | `requirements.txt`                  | xxh3_128 content hashing for duplicate detection |
| jsonschema        | ≥ 4.17.3   | `requirements.txt`                  | JSON schema validation (file metadata) |
| pytest-qt         | ≥ 4.4.0    | `requirements.txt`                  | Dev only — `QApplication` fixtures; also pulls in `pytest` |
| pytest-timeout    | ≥ 2.4.0    | `requirements.txt`                  | Dev only — per-test timeout guard |
| pyinstaller       | ≥ 5.11.0   | installed separately                | Build only — produces standalone `.exe` files; not in `requirements.txt` |

---

## Prerequisites

The following system-level tools must be installed on your Windows machine **before** running any
step in [Development Setup](#development-setup). Python packages (`requirements.txt`) are handled
by pip during setup — only the tools below need manual installation.

| Tool | Version | Required for | How to install |
|---|---|---|---|
| **Python** | **3.13 exactly** | Runtime; `run.py`; tests | [python.org/downloads](https://www.python.org/downloads/) — tick **"Add Python to PATH"** |
| **Git** | ≥ 2.40 | Clone the repository | [git-scm.com](https://git-scm.com/download/win) |
| **Docker Desktop** | ≥ 4.x | Build the TauSync `.dll` (step 3) | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| **Visual Studio Build Tools 2022** | 2022 | Build the native C++ pipe module (step 4) | [VS Downloads → Build Tools](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022) — select the **"Desktop development with C++"** workload |
| **CMake** | ≥ 3.20 | Configure & build the pipe module | Bundled with the C++ workload above; or [cmake.org](https://cmake.org/download/) (add to PATH) |
| **.NET 8 SDK** | 8.x | Package the MSI installer; WiX toolset | [dotnet.microsoft.com/download/dotnet/8.0](https://dotnet.microsoft.com/download/dotnet/8.0) |
| **WiX Toolset** | ≥ 4.x | Create the `.msi` production package | `dotnet tool install --global wix` (requires .NET SDK above) |
| **OBS Studio** (with Virtual Camera) | ≥ 29.x | Camera Mirror feature — `pyvirtualcam` uses the OBS Virtual Camera driver as its backend | [obsproject.com/download](https://obsproject.com/download) — the driver is installed automatically with OBS |

### Installing the prerequisites

Follow these steps in order — some tools depend on others (WiX requires .NET; CMake is bundled
inside the VS Build Tools installer).

#### 1. Python 3.13

1. Go to [python.org/downloads](https://www.python.org/downloads/) and download the **Python 3.13**
   Windows installer (64-bit).
2. Run the installer. On the first screen, tick **both** checkboxes before clicking *Install Now*:
   - ☑ **Add Python 3.13 to PATH**
   - ☑ **Install launcher for all users**
3. Verify:
   ```powershell
   python --version   # must print Python 3.13.x
   ```

> **Version is exact, not a minimum.** `match` statements, `A | B` union syntax, and `f`-string
> `=` specifiers are used throughout the codebase — Python 3.11 / 3.12 will not work.

#### 2. Git

1. Download the Windows installer from [git-scm.com/download/win](https://git-scm.com/download/win).
2. Run with default options (the defaults are fine for all prompts).
3. Verify:
   ```powershell
   git --version   # must print git version 2.40 or later
   ```

#### 3. Docker Desktop

Docker is the easiest way to build the TauSync `.dll` — no local .NET SDK required.

1. Download Docker Desktop from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/).
2. Run the installer. When prompted, choose the **WSL 2** backend (recommended over Hyper-V).
3. After installation, launch **Docker Desktop** and wait for the engine to reach *Running* state
   (green icon in the system tray).
4. Verify:
   ```powershell
   docker --version        # e.g. Docker version 26.x.x
   docker info             # must not show "ERROR" — confirms the daemon is running
   ```

> **Docker must be running** whenever you execute `docker compose up` in step 3 of
> [Development Setup](#development-setup). Starting Docker Desktop before opening a terminal is
> a good habit.

#### 4. Visual Studio Build Tools 2022 (C++ workload)

This installs the MSVC compiler, the Windows SDK, and CMake — everything needed to build the
native C++ pipe module. The full Visual Studio IDE is **not** required.

1. Go to [visualstudio.microsoft.com/downloads](https://visualstudio.microsoft.com/downloads/)
   and download **Build Tools for Visual Studio 2022** (under *Tools for Visual Studio*).
2. Run `vs_BuildTools.exe`. In the workload selector, tick:
   - ☑ **Desktop development with C++**
     (This automatically includes MSVC v143, Windows 11 SDK, and CMake tools.)
3. Click **Install** and wait for the download + install to complete (~3–6 GB).
4. Verify by opening **Developer Command Prompt for VS 2022** (Start menu) and running:
   ```cmd
   cl           # prints: Microsoft (R) C/C++ Optimizing Compiler ...
   cmake --version   # prints: cmake version 3.x
   ```

> **Use the Developer Command Prompt** (not plain PowerShell) when running the `cmake` build
> commands in setup step 4, so that MSVC is on the PATH.

#### 5. CMake (standalone — only if skipping VS Build Tools)

CMake is **bundled** with the VS Build Tools C++ workload (step 4). Install it standalone only
if you have an existing MSVC installation without CMake, or need a newer version.

1. Download the Windows installer from [cmake.org/download](https://cmake.org/download/).
2. During install, select **Add CMake to the system PATH for all users**.
3. Verify:
   ```powershell
   cmake --version   # must print 3.20 or later
   ```

#### 6. .NET 8 SDK

Required to package the MSI (`dotnet build`) and to install WiX. Also the fallback for building
the TauSync DLL without Docker.

1. Go to [dotnet.microsoft.com/download/dotnet/8.0](https://dotnet.microsoft.com/download/dotnet/8.0).
2. Download and run the **SDK** installer for Windows x64 (not the Runtime-only package).
3. Verify:
   ```powershell
   dotnet --version   # must print 8.x.x
   ```

#### 7. WiX Toolset

WiX is installed as a .NET global tool — the .NET 8 SDK (step 6) must be installed first.

```powershell
dotnet tool install --global wix
```

Verify:

```powershell
wix --version   # prints: 4.x.x
```

> If `wix` is not found after install, close and reopen your terminal so the PATH is refreshed.

#### 8. OBS Studio (Virtual Camera driver)

`pyvirtualcam` requires a virtual camera driver. The easiest way to get it on Windows is to install
OBS Studio — the **OBS Virtual Camera** driver is bundled and registered automatically during setup.

1. Download OBS Studio from [obsproject.com/download](https://obsproject.com/download).
2. Run the installer with default options (no additional components need to be ticked).
3. After installation you do **not** need to launch OBS — the driver is registered system-wide and
   `pyvirtualcam` will find it automatically at runtime.
4. Verify the driver is present by opening **Device Manager → Cameras**: you should see
   **OBS Virtual Camera** listed.

> **Camera Mirror only.** The OBS driver is only needed when using the Camera Mirror feature.
> All other SyncDose features (file transfer, backup, device info, clipboard) work without it.

---

## Development Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd Ecosystem
```

### 2. Create and activate a virtual environment

```powershell
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

`pythonnet` (TauSync's CLR bridge) conflicts with other packages when installed globally — always use a venv.

### 3. Build the TauSync DLL

`tausync_py` wraps a compiled .NET 8 assembly. Build it with Docker Compose from the `TauSync/` directory:

```bash
cd TauSync/
docker compose up
```

This compiles `TauSync.Lib.csproj` inside a `mcr.microsoft.com/dotnet/sdk:8.0` container and writes the
output to `TauSync/windows/tausync_py/dll/`. Docker is the only prerequisite — no local .NET SDK needed.

> **Without Docker:** Install the [.NET 8 SDK](https://dotnet.microsoft.com/download) and run:
> ```bash
> cd TauSync/Tausync_Windows/TauSync.Lib/
> dotnet publish -c Release -o ../../../windows/tausync_py/dll/
> ```

After a successful build you should see:
```
TauSync/windows/tausync_py/dll/
├── TauSync.Lib.dll        ← loaded by pythonnet at runtime
├── TauSync.Lib.deps.json
└── TauSync.Lib.pdb
```

### 4. Build the native named-pipe module

The IPC between `SyncDose.exe` and `FileHandler.exe` uses a C++ pybind11 module. Build it with MSVC:

```powershell
cmake -S desktop/native/windows/pipe -B desktop/native/windows/pipe/build
cmake --build desktop/native/windows/pipe/build --config Release
Copy-Item desktop/native/windows/pipe/build/Release/pipe_module.cp313-win_amd64.pyd `
          desktop/native/windows/pipe/
```

### 5. Install Python dependencies

```powershell
cd desktop/
pip install -r ../TauSync/windows/requirements.txt   # pythonnet
pip install -r ../FileDetection/requirements.txt     # ML screening pipeline (BackupService)
pip install -r requirements.txt
pip install ../TauSync/windows                        # tausync_py (includes the DLL from step 3)
```

### 6. Compile Qt resources

Icons and QSS stylesheets are embedded in the compiled `resources_qrc.py` module. `run.py` does this
automatically, but to do it manually:

```bash
pyside6-rcc resources/syncdose.qrc -o resources_qrc.py
```

`resources_qrc.py` is auto-generated — do not edit it. Re-run this command whenever you add a new asset.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `pyside6-rcc: command not found` | PySide6 not installed or venv inactive | Activate venv, `pip install -r requirements.txt` |
| `ModuleNotFoundError: resources_qrc` | Resources not compiled | Run `pyside6-rcc resources/syncdose.qrc -o resources_qrc.py` |
| `FileNotFoundError: TauSync.Lib.dll not found` | DLL not built | Complete step 3 |
| `0xC0000409` fatal crash | TauSync called from a `QThread` | Never use `QThread` for TauSync I/O — use `threading.Thread` |
| Qt window blank / unstyled | `resources_qrc.py` stale | Delete and recompile |
| Phone drive not appearing / VirtualDrive.exe exits immediately | WinFSP not installed | Install WinFSP 2.0 from [winfsp.dev](https://winfsp.dev) — check `HKLM\Software\WinFsp` |
| `VirtualDrive.exe not found` logged at startup | Binary missing from build output | The pre-built binary must be at `native/windows/virtual_drive/build/Release/VirtualDrive.exe`; do not rebuild from source (missing headers) |

---

## Running the App

### Development launcher (recommended)

```bash
python run.py
```

`run.py` always executes three steps in order:

1. **Compile resources** — runs `pyside6-rcc resources/syncdose.qrc -o resources_qrc.py`
2. **Run all tests** — runs `pytest . -v` from the `desktop/` root; aborts with a non-zero exit
   code if any test fails, so the app never launches against a broken build
3. **Launch the app** — spawns `python main.py` in a subprocess

### Direct launch (skip compile + tests)

```bash
python main.py
```

`main.py` creates the `QApplication`, defers all `QObject` imports until after it exists (required
because several singletons are instantiated at module level), then shows `MainWindow`. Use this when
you know the resources are already compiled and want a faster iteration loop.

---

## Running Tests

Tests live in `desktop/tests/` and are organised by layer:

```bash
# Run the full test suite from the desktop/ directory
pytest .

# Run a single module verbosely
pytest tests/repositories/test_tool.py -v

# Run with coverage (requires pytest-cov)
pytest . --cov=. --cov-report=term-missing
```

`pytest-qt` is required even for tests that do not open windows — `DeviceViewModel` and
`FileTransferViewModel` instantiate `QObject` subclasses, which require a running `QApplication`.
The `pytest-qt` plugin provides the `qtapp` fixture automatically.

---

## Production Build

The production install ships three executables packaged into a single bootstrapper installer
(`SyncDoseSetup.exe`):

| Executable | How it is built | Purpose |
|---|---|---|
| `SyncDose.exe` | PyInstaller | Main dashboard app |
| `FileHandler.exe` | PyInstaller | Windows shell "Send with SyncDose" helper |
| `VirtualDrive.exe` | Pre-built C++ binary | WinFsp filesystem that mounts the phone as a drive letter |

### Step 1 — Build the PyInstaller executables

Resources must already be compiled (`pyside6-rcc`) before running PyInstaller.

```powershell
# Run from the repo root (Ecosystem/)
pyinstaller desktop/installer/Package/specs/main_app.spec      # → dist/SyncDose/SyncDose.exe
pyinstaller desktop/installer/Package/specs/file_handler.spec  # → dist/FileHandler/FileHandler.exe
```

> **VirtualDrive.exe is pre-built** — the compiled binary lives at
> `desktop/native/windows/virtual_drive/build/Release/VirtualDrive.exe` and is bundled
> automatically by `main_app.spec` via its `binaries=[…VirtualDrive.exe…]` entry.
> **Do not attempt to rebuild it from source** — `ClientNamedPipe.h` and `PipeException.h`
> are missing from `src/`, so CMake will fail. The existing binary is fully functional.

### Step 2 — Package as MSI + Bundle

```powershell
# Produces desktop/installer/Bundle/bin/Release/SyncDoseSetup.exe
dotnet build desktop/installer/ -c Release
```

`dotnet build` invokes WiX to produce two outputs:

- **`Package.msi`** — harvests `dist/SyncDose/` and `dist/FileHandler/` recursively, registers
  the shell context-menu verb (`HKCR\*\shell\SendWithSyncDose`), and creates Start Menu / Desktop
  shortcuts.
- **`SyncDoseSetup.exe`** (Bundle) — wraps `Package.msi` and silently downloads and installs
  any missing prerequisites at runtime:
  - **.NET 8 x64 Runtime** — required by `pythonnet` / TauSync CLR bridge
  - **WinFSP 2.0** — required by `VirtualDrive.exe`

`SyncDoseSetup.exe` is the only file end users need. The MSI is uploaded as an artifact by CI
(`desktop.yml` → `build` job). See the [CI/CD section in the root README](../README.md#cicd)
for the full pipeline.

### Why three executables?

`SyncDose.exe` is the main dashboard and acts as a named-pipe server on both
`\\.\pipe\FileSend` and `\\.\pipe\SyncDoseVDrive`.

`FileHandler.exe` (`core/file_handler.py`) is registered as the Windows shell "Send with SyncDose"
right-click handler. When invoked by the OS it connects to `\\.\pipe\FileSend`, writes the
target file path, and exits. `SyncDose.exe` reads the path and initiates the file send to the
phone. See [File Transfer & IPC](#file-transfer--ipc).

`VirtualDrive.exe` is a native C++ WinFsp filesystem. It mounts the phone as a Windows drive
letter and forwards every Explorer operation (list, stat, read, write, create, delete, rename)
to `SyncDose.exe` over `\\.\pipe\SyncDoseVDrive`. `SyncDose.exe` translates each op into a
TauSync round-trip to the Android app. `VirtualDriveService` launches and supervises the
process; it is started on device connect and stopped on device disconnect.

---

## Project Structure

```
desktop/
│
├── run.py                          # Dev launcher: compile resources → run tests → start app
├── main.py                         # Entry point: QApplication + deferred imports + MainWindow
├── requirements.txt                # Runtime + dev deps (PySide6, pytest-qt, qrcode…)
├── resources_qrc.py                # AUTO-GENERATED by pyside6-rcc — do not edit
│
├── data/                           # Runtime data (created automatically on first launch)
│   ├── app.db                      # SQLite database (devices + tools tables)
│   ├── syncdose.log                # Rotating application log
│   └── virtualdrive.log            # VirtualDrive.exe stdout/stderr capture
│
├── app/                            # Application-level singletons (not domain logic)
│   ├── app_state.py                # AppState — the single DI root (see Architecture)
│   ├── navigation_manager.py       # NavigationManager singleton + navigate(int) Signal
│   └── theme_manager.py            # ThemeManager singleton — tracks Windows dark/light scheme
│
├── core/
│   └── file_handler.py             # Entry point for FileHandler.exe — writes path to named pipe
│
├── domain/
│   ├── dto/                        # Data Transfer Objects — lightweight, view-facing dataclasses
│   │   ├── device_info.py          # DeviceInfoDTO family (DeviceNameDTO, DeviceOSDTO, …)
│   │   ├── file_metadata.py        # FileMetadataDTO (name, size)
│   │   ├── previous_device.py      # PreviousDeviceDTO (login screen device list)
│   │   └── tool.py                 # ToolDTO
│   ├── entities/                   # Domain entities — canonical typed dataclasses
│   │   ├── device_info.py          # DeviceEntity (id, name, os, tag, battery, storage, ip, …)
│   │   └── tool.py                 # ToolEntity (title, description, icon_path, is_enabled)
│   └── enums/                      # Typed enumerations — always use these, never raw strings
│       ├── channel.py              # Channel StrEnum — generic TauSync channel IDs
│       ├── device_info_channels.py # DeviceInfoChannels — per-field channel names for device info
│       ├── device_status.py        # DeviceStatus (ONLINE, RECENT, IDLE) — login card badges
│       ├── device_type.py          # DeviceType (DEVICE_NAME, DEVICE_TYPE, BATTERY, STORAGE)
│       ├── file_transfer_channels.py  # FileTransferChannels — metadata / response / data channels
│       ├── file_transfer_response.py  # FileTransferResponse (ACCEPTED_FROM_PC, REJECTED_FROM_ANDROID…)
│       ├── screen.py               # Screen IntEnum (LOGIN = 0, DASHBOARD = 1)
│       ├── session_channels.py     # SessionChannels — DISCONNECT_FROM_PHONE, DISCONNECT_FROM_PC
│       ├── backup_channels.py      # BackupChannels — control + per-file result channel names
│       ├── backup_file_result.py   # BackupFileResult (ACCEPTED, REJECTED, NEEDS_REVIEW, …)
│       ├── backup_status.py        # BackupStatus — overall backup session state machine
│       ├── virtual_drive_channels.py  # VirtualDriveChannels — list / stat / read / write / … op names
│       └── clipboard_channels.py   # ClipboardChannels — CLIPBOARD_ANDROID_TO_PC / CLIPBOARD_PC_TO_ANDROID
│
├── native/
│   └── windows/
│       ├── pipe/                   # C++ pybind11 named-pipe module (Server / Client classes)
│       └── virtual_drive/          # C++ WinFsp filesystem (VirtualDrive.exe) — pre-built binary
│
├── repositories/                   # Data-access layer — SQLite via sqlite3
│   ├── repository.py               # IRepository[T, K] abstract base (get_by_id, get_all, save, delete)
│   ├── device.py                   # DeviceRepository — devices table; emits entity_saved / entity_deleted
│   └── tool.py                     # ToolRepository — tools table; seeds 1 default tool on first run
│
├── resources/                      # Design tokens and Qt virtual filesystem paths
│   ├── colors.py                   # Palette → Colors (dark) + LightPalette → LightColors (light)
│   │                               # Plus component-scoped token classes for every widget
│   ├── spacing.py                  # Spacing scale: XS=4 · SM=8 · MD=12 · LG=16 · XL=20 · XXL=24 px
│   ├── paths.py                    # StrEnum paths into Qt virtual filesystem
│   │                               # (Icons, Styles, NavigationStyles, DashboardStyles, …)
│   ├── syncdose.qrc                # Qt resource manifest — lists every icon and QSS to embed
│   ├── icons/                      # SVG icons (logo, battery, storage, android, smartphone, …)
│   └── styles/                     # Per-component QSS stylesheets (mirrors the views/ tree)
│
├── serializers/                    # Convert entities ↔ SQLite row tuples / JSON
│   ├── serializer.py               # ISerializer[T, K] abstract base (serialize / deserialize)
│   ├── device.py                   # DeviceSerializer — DeviceEntity ↔ 10-column row tuple
│   ├── file_metadata.py            # FileMetadataSerializer — FileMetadataDTO ↔ JSON string
│   ├── tool.py                     # ToolSerializer — ToolEntity ↔ 4-column row tuple
│   ├── backup_session.py           # BackupSessionSerializer — BackupSessionPromptDTO ↔ JSON
│   └── schemas/                    # JSON Schema files for validating wire-format payloads
│       └── file_metadata.json      # Schema for the file-metadata channel payload
│
├── services/                       # Background services — all I/O on daemon threads, never QThread
│   ├── connectivity.py             # ConnectivityService — TauSync TCP lifecycle
│   ├── device_info.py              # DeviceInfoService — reads device channels, persists entity
│   ├── file_transfer.py            # FileTransferService — send/receive files + named-pipe listener
│   ├── phone_request.py            # PhoneRequestService — polls peer waiting channels, dispatches
│   ├── tool.py                     # ToolService — wraps ToolRepository, re-emits its signals
│   ├── backup.py                   # BackupService — receives backup files, runs FileDetection pipeline
│   ├── virtual_drive.py            # VirtualDriveService — bridges VirtualDrive.exe ↔ Android via TauSync
│   └── clipboard.py                # ClipboardService — two-directional clipboard sync; SHA-256 anti-loop guard
│
├── utils/                          # Shared utilities (no singletons here)
│   ├── meta.py                     # ABCQObjectMeta — metaclass bridging ABC and QObject
│   ├── network.py                  # get_ip_by_hostname(), read_string_from_channel()
│   ├── styles.py                   # load_stylesheet(), themed() — QSS loading helpers
│   ├── db.py                       # sqlite_connection() — context-manager for short-lived connections
│   └── file_type.py                # File-type helpers used by BackupService
│
├── viewmodels/                     # PySide6 QObject ViewModels — DTOs + Signals
│   ├── device.py                   # DeviceViewModel — drives login list + dashboard device cards
│   ├── file_transfer.py            # FileTransferViewModel — gates send/receive behind connectivity
│   ├── tool.py                     # ToolViewModel — drives the tools grid
│   └── backup.py                   # BackupViewModel — backup session state + review queue
│
├── views/
│   ├── main_window.py              # MainWindow — QStackedWidget + system tray
│   ├── layouts/
│   │   └── flow_layout.py          # FlowLayout — wraps children like inline text (used in ToolsGrid)
│   ├── screens/
│   │   ├── login.py                # LoginScreen — LeftPanel + RightPanel in 5:6 stretch ratio
│   │   └── dashboard.py            # DashboardScreen — Sidebar + Topbar + DashboardContent
│   └── widgets/
│       ├── dashboard/
│       │   ├── battery_info.py         # BatteryInfo — circular gauge with charging indicator
│       │   ├── dashboard_content.py    # DashboardContent — assembles the full content area
│       │   ├── info_card.py            # InfoCard — generic stat card (icon + label + value)
│       │   ├── phone_details_row.py    # PhoneDetailsRow — device name / OS / tag row
│       │   ├── storage_info.py         # StorageInfo — bar with used / total labels
│       │   ├── tool_card.py            # ToolCard — single tool tile
│       │   ├── tools_grid.py           # ToolsGrid — FlowLayout container for ToolCard widgets
│       │   └── tools_section_header.py # ToolsSectionHeader — section title + subtitle
│       ├── dialogs/
│       │   └── file_handler.py         # TransferErrorDialog — shown on file transfer errors
│       ├── indicators/
│       │   ├── connection_pill.py      # ConnectionPill — CONNECTED / DISCONNECTED badge
│       │   ├── pill_wraper.py          # PillWrapper — layout host for ConnectionPill
│       │   └── pulsing_dot.py          # PulsingDot — animated dot for "Waiting…" indicator
│       ├── login/
│       │   ├── left_panel.py           # LeftPanel — QR code + Refresh button + PulsingDot
│       │   ├── previous_device_card.py # PreviousDeviceCard — hover-to-connect device entry
│       │   ├── qr.py                   # QR — QR code image with rounded corners + brackets
│       │   └── right_panel.py          # RightPanel — scrollable previously connected devices
│       ├── navigation/
│       │   ├── container.py            # NavigationContainer — sidebar + main content wrapper
│       │   ├── item.py                 # NavigationItem — single icon-based nav item
│       │   └── sidebar.py              # Sidebar — vertical strip of NavigationItems + logo
│       ├── loading/
│       │   ├── overlay.py              # LoadingOverlay — full-widget translucent blocking layer
│       │   └── spinner.py              # LoadingSpinner — animated spinner widget
│       ├── toasts/
│       │   └── file_received.py        # FileReceivedToast — accept/reject prompt for incoming file
│       ├── backup/
│       │   ├── backup_dest_picker_dialog.py         # Dialog to choose backup destination folder
│       │   ├── backup_review_dialog.py               # Review dialog — shows files needing user decision
│       │   ├── backup_classification_review_dialog.py# ML-flagged file review (NEEDS_REVIEW items)
│       │   ├── backup_progress_window.py             # Live progress window during a backup session
│       │   ├── backup_review_model.py                # QAbstractListModel for review item list
│       │   ├── backup_progress_model.py              # QAbstractListModel for progress item list
│       │   ├── backup_review_delegate.py             # Custom item delegate for the review list
│       │   ├── backup_progress_delegate.py           # Custom item delegate for the progress list
│       │   └── helpers.py                            # Shared formatting helpers for backup widgets
│       ├── bar.py                      # Bar — generic horizontal separator bar
│       ├── divider.py                  # Divider — thin horizontal rule between sections
│       ├── logo_widget.py              # LogoWidget — SVG logo with gradient text
│       └── topbar.py                   # Topbar — ConnectionPill + device status + Disconnect button
│
└── tests/
    ├── conftest.py                 # Shared pytest fixtures (in-memory repos, mock services)
    ├── repositories/
    │   ├── test_device.py
    │   └── test_tool.py
    ├── serializers/
    │   ├── test_serializer_device_info.py
    │   ├── test_serializer_previous_device.py
    │   └── test_serializer_tool.py
    ├── services/
    │   ├── test_connectivity.py
    │   ├── test_clipboard.py
    │   ├── test_file_transfer.py
    │   ├── test_phone_request.py
    │   └── test_webcam.py
    ├── utils/
    │   ├── test_network.py
    │   └── test_styles.py
    └── viewmodels/
        ├── test_viewmodel_device_info.py
        ├── test_viewmodel_file_transfer.py
        ├── test_viewmodel_previous_device.py
        └── test_viewmodel_tool.py
```

---

## Architecture

SyncDose follows **MVVM with a Services layer**. The full dependency chain:

```
Views
  └─ bind to ──► ViewModels  (DTOs + Signals)
                   └─ consume ──► Services  (background threads, TauSync I/O)
                                    └─ use ──► Repositories  (SQLite via sqlite3)
                                                 └─ use ──► Serializers  (entity ↔ row tuple)
```

The Services layer is what separates this from a plain repository-in-ViewModel pattern:

- **Repositories** are pure SQLite data stores — no networking, no threading of their own.
- **Services** own all network I/O and background threading. They read from repositories and
  emit results via Qt Signals so ViewModels never directly touch a database or a TauSync stream.
- **ViewModels** subscribe to Service signals, convert entities to DTOs, and re-emit
  view-ready signals. They never import from `repositories/` directly.
- **Views** are PySide6 widgets that bind to ViewModel signals and call ViewModel methods.
  They never import from `services/` or `repositories/`.

---

## DI Root — AppState

`app/app_state.py` constructs and wires every singleton exactly once at import time.
A module-level `app_state` instance is the only object that needs to be imported from this module.
**Never instantiate repositories, services, or viewmodels anywhere else.**

```python
# app/app_state.py (simplified)
class AppState:
    def __init__(self) -> None:
        # Repositories
        self.tools_repository    = ToolRepository()
        self.device_repository   = DeviceRepository()

        # Services
        self.connectivity_service   = ConnectivityService()
        self.device_info_service    = DeviceInfoService(connectivity, device_repository)
        self.file_transfer_service  = FileTransferService(connectivity)
        self.tool_service           = ToolService(tools_repository)
        self.backup_service         = BackupService(connectivity)
        self.clipboard_service      = ClipboardService(connectivity)

        # ViewModels
        self.device_viewmodel        = DeviceViewModel(connectivity_service, device_info_service)
        self.file_transfer_viewmodel = FileTransferViewModel(file_transfer_service, connectivity_service)
        self.tool_viewmodel          = ToolViewModel(tool_service)
        self.backup_viewmodel        = BackupViewModel(backup_service, connectivity_service)

        # VirtualDriveService bridges VirtualDrive.exe ↔ Android; depends on device_info_service
        self.virtual_drive_service  = VirtualDriveService(connectivity, device_info_service)

        # PhoneRequestService depends on backup_service — constructed after viewmodels
        self.phone_request_service  = PhoneRequestService(connectivity, file_transfer_service, backup_service)

        # Lifecycle wiring: start/stop services on device connection events
        self.device_viewmodel.device_connected.connect(self.backup_service.start)
        self.device_viewmodel.device_connected.connect(self.phone_request_service.start)
        self.device_viewmodel.device_connected.connect(self.virtual_drive_service.start)
        self.device_viewmodel.device_disconnected.connect(self.backup_service.stop)
        self.device_viewmodel.device_disconnected.connect(self.phone_request_service.stop)
        self.device_viewmodel.device_disconnected.connect(self.virtual_drive_service.stop)

app_state: Final[AppState] = AppState()
```

The two other important module-level singletons live in their own files so they can be imported
without pulling in all of `AppState`:

| Singleton | Module | Purpose |
|---|---|---|
| `app_state` | `app/app_state.py` | DI root — owns all repos, services, viewmodels |
| `navigation_manager` | `app/navigation_manager.py` | Emits `navigate(int)` Signal to switch screens |
| `theme_manager` | `app/theme_manager.py` | Tracks Windows dark/light scheme; emits `theme_changed` |

`main.py` imports `theme_manager` before constructing any widget so `theme_manager.is_dark` is
already correct when the first `_setup_style()` call runs.

---

## Layer Boundaries

| Layer | May import from | Must NOT import from |
|---|---|---|
| Views | ViewModels, DTOs, `resources/` | Repositories, Entities, Services directly |
| ViewModels | Services, Entities, DTOs | Views, Repositories |
| Services | Repositories, Entities, `tausync_py` | Views, ViewModels |
| Repositories | Serializers, Entities | Views, ViewModels, Services |

Violating these boundaries breaks testability. For example, if a ViewModel imports from
`repositories/` directly, the test must provide a real repository (with a real SQLite file) even
when testing only ViewModel logic.

---

## Threading Rules

**Never call TauSync blocking methods from a `QThread`.**

TauSync uses pythonnet's CLR bridge to call blocking .NET async methods. Running these from a
Qt-managed native thread corrupts the CLR thread stack and causes a fatal `0xC0000409` crash.

**Rule:** All TauSync I/O runs on `threading.Thread(daemon=True)`. Every service follows the same
pattern — a `_spawn()` helper creates a daemon thread, appends it to `self._threads`, and starts it.
A `_lifecycle_lock` serializes `start()` / `stop()` calls; `_is_running` (a `threading.Event`)
gates new work from being spawned during teardown.

PySide6 delivers cross-thread `Signal.emit()` calls safely via queued connections — no manual
`QMetaObject.invokeMethod` needed.

---

## Screen Navigation

`MainWindow` holds a `QStackedWidget` with two screens at fixed indices:

```
index 0 — LoginScreen      (shown on launch, and after a device disconnects)
index 1 — DashboardScreen  (shown after a device connects)
```

Navigation is driven exclusively by `navigation_manager.go_to_screen(Screen.X)`:

```python
from app.navigation_manager import navigation_manager
from domain.enums.screen import Screen

navigation_manager.go_to_screen(Screen.DASHBOARD)  # → triggers DashboardScreen
navigation_manager.go_to_screen(Screen.LOGIN)       # → triggers LoginScreen
```

`MainWindow._connect_signals()` wires `navigation_manager.navigate` → `_change_page(index)`.
`MainWindow` never decides *when* to navigate — it only executes the switch when told to.
This keeps `MainWindow` free of business logic and makes navigation trivially testable.

Who triggers navigation in practice:

| Event | Signal chain | Outcome |
|---|---|---|
| Device connects | `ConnectivityService.device_connected` → `DeviceViewModel._on_device_connected` → `navigation_manager.go_to_screen(DASHBOARD)` | Dashboard shown |
| Device disconnects | `ConnectivityService.device_disconnected` → `DeviceViewModel._on_device_disconnected` → `navigation_manager.go_to_screen(LOGIN)` | Login shown |

---

## Theming System

`ThemeManager` (`app/theme_manager.py`) reads the current system color scheme from the Windows
registry at startup (Qt's `colorScheme()` is unreliable on some Windows configurations) and
re-emits `theme_changed` whenever the user changes the system preference at runtime.

```python
from app.theme_manager import theme_manager

# Read current scheme
if theme_manager.is_dark:
    ...

# React to changes (e.g., in a widget's __init__)
theme_manager.theme_changed.connect(self._setup_style)
```

Widgets that support theming call a `_setup_style()` method that loads the correct QSS template,
substituting color token values using the `themed([Colors], [LightColors], theme_manager.is_dark)`
helper from `utils/styles.py`. QSS templates reference color tokens by name using Python format
strings, e.g. `background: {SURFACE_PRIMARY};`.

---

## Design Tokens

The design system is a two-layer token hierarchy split into dark and light variants.

### `resources/colors.py`

**Layer 1 — raw palette** (never reference directly in widgets):

| Class | Contents |
|---|---|
| `Palette` | Raw hex values for the dark theme (e.g. `DARK_900 = "#111827"`) |
| `LightPalette` | Mirror of `Palette` with light-theme hex values (same member names) |

**Layer 2 — semantic roles** (always use these in widgets):

| Class | Contents |
|---|---|
| `Colors` | Semantic dark-theme tokens: `SURFACE_PRIMARY`, `TEXT_PRIMARY`, `ACCENT_TEAL`, etc. |
| `LightColors` | Mirror of `Colors` for the light theme (same member names) |

**Component-scoped tokens** (use in the specific widget only):

`SidebarColors`, `NavigationColors`, `DashboardColors`, `InfoCardColors`, `ToolCardColors`,
`LoginColors`, `TopbarColors`, `FileReceivedToastColors`, `HandlerDialogColors`, `LogoColors`, …
and their `Light*` mirrors.

**Rule:** Always reference `Colors.TEXT_PRIMARY` (or its light mirror), never `Palette.SLATE_100`.
This keeps every widget one step removed from raw hex values so the entire palette can be rethemed
by swapping one class.

### `resources/spacing.py`

Fixed scale constants (in px) for margins, padding, and gaps:

```
XS = 4   SM = 8   MD = 12   LG = 16   XL = 20   XXL = 24
```

---

## Services

All services share the same internal lifecycle pattern:

- `start()` / `stop()` kick off daemon `threading.Thread` workers
- `_spawn(target, *args)` creates, registers, and starts a thread; rejected during teardown
- `_lifecycle_lock: threading.Lock` serializes concurrent start/stop calls
- `_is_running: threading.Event` gates new work; cleared on `stop()`

### `ConnectivityService`

Manages the TauSync TCP connection lifecycle. Supports two connection modes:

- **Bluetooth (default)** — calls `tau.connect_hybrid()`, which advertises a BLE beacon so the
  phone can discover the PC by name. Requires the user to approve the first connection via a
  dialog; subsequent connections from the same phone are auto-approved.
- **Wi-Fi** — calls `tau.listen()` (plain TCP). The phone connects by scanning a QR code
  that encodes this PC's local IP.

The active mode is toggled at runtime with `set_mode(use_bluetooth: bool)`.

| Signal | Payload | When |
|---|---|---|
| `device_connected` | — | A phone connects in either mode |
| `device_disconnecting` | — | Teardown starts (transport still open) |
| `device_disconnected` | — | Transport closed; safe to call `start()` to re-listen |
| `connection_error` | `str` | Unexpected exception while listening (not a normal stop) |
| `mode_changed` | `bool` | `set_mode()` changed the active mode; `True` = BT, `False` = Wi-Fi |
| `phone_approval_requested` | `str` | New (unknown) phone is asking to connect over BT — show approve/reject dialog; call `resolve_phone_approval()` to unblock |

`disconnect_device()` checks whether the phone sent a disconnect first (via
`SessionChannels.DISCONNECT_FROM_PHONE`). If not, it notifies the phone
(`SessionChannels.DISCONNECT_FROM_PC`) before closing the transport.

The shared `tau` property exposes the `TauSync` instance so other services can open channels
on the same transport without owning it.

### `DeviceInfoService`

Reads all device metadata from TauSync named channels and emits a fully-populated `DeviceEntity`.
Uses a unique-ID handshake: reads the device's current ID from `DeviceInfoChannels.ID`; if empty,
generates a new UUID that doesn't clash with any stored device and writes it back.

| Signal | Payload | When |
|---|---|---|
| `device_info_ready` | `DeviceEntity` | All channel reads complete; entity persisted |
| `device_saved` | `DeviceEntity` | Entity written to the repository |
| `device_fetched` | `DeviceEntity \| None` | `fetch_device_by_id()` completes |
| `all_devices_fetched` | `list[DeviceEntity]` | `fetch_all_devices()` completes |
| `read_error` | `str` | Any channel read raises |

### `FileTransferService`

Sends and receives files over TauSync channels. Also listens on the named pipe
`\\.\pipe\FileSend` for paths written by `FileHandler.exe` (the shell context-menu
helper) and routes them through the same `send_file()` path.

See [File Transfer & IPC](#file-transfer--ipc) for the full protocol.

| Signal | Payload | When |
|---|---|---|
| `file_send_complete` | `(str, int)` filename + bytes | Send succeeded |
| `file_send_rejected` | `str` filename | Receiver declined |
| `file_send_error` | `str` | Any send failure |
| `file_metadata_received` | `(str, int)` filename + size | Incoming file metadata arrived — show prompt |
| `file_receive_complete` | `(str, str)` filename + path | Receive succeeded |
| `file_receive_error` | `str` | Any receive failure |

### `BackupService`

Receives backup files sent from the Android app and runs each file through the
`FileDetection` screening pipeline (`Classifier`).

For every incoming file the service:
1. Streams the file bytes to a temporary cache location.
2. Calls `Classifier.classify(cached_file, dest_path, use_ml=True)`.
3. Moves `ACCEPTED` files to the chosen destination folder.
4. Drops `REJECTED` files (duplicates or confidently unwanted images).
5. Queues `NEEDS_REVIEW` files and emits a signal so `BackupViewModel` can surface them
   in the `BackupClassificationReviewDialog`.

`BackupService` is started by `device_viewmodel.device_connected` and stopped on
`device_viewmodel.device_disconnected` (wired in `AppState.__init__`).

| Signal | Payload | When |
|---|---|---|
| `backup_session_started` | `BackupSessionPromptDTO` | Android initiates a backup session |
| `backup_review_needed` | `list[BackupReviewPromptDTO]` | Files needing user decision queued |
| `backup_file_result` | `(str, BackupFileResult)` | Per-file verdict ready |
| `backup_session_complete` | — | All files in the session processed |
| `backup_error` | `str` | Unrecoverable error in the session |

### `VirtualDriveService`

Bridges `VirtualDrive.exe` (a WinFsp native filesystem) to the connected Android device via
TauSync. SyncDose.exe listens on `\\.\pipe\SyncDoseVDrive` (byte-stream mode); VirtualDrive.exe
connects and sends framed requests using a `[4B jsonLen][4B payloadLen][json][payload]` protocol.

For every incoming filesystem op the service opens a **unique `{op}_{uuid8}` TauSync meeting word**
(e.g. `virtual_drive_stat_a1b2c3d4`) so that concurrent Explorer requests never collide on the same
channel — both TauSync's `_inFlightWords` guard and Android's `inProgressChannels` guard reject a
second simultaneous `connect()` on the same word.

**Op routing:**

| Op | TauSync channel | Notes |
|---|---|---|
| `list` | `VirtualDriveChannels.VIRTUAL_DRIVE_LIST` | JSON request/response — directory listing |
| `list_page` | `VirtualDriveChannels.VIRTUAL_DRIVE_LIST_FULL` | Paginated listing (cursor-based) |
| `stat` | `VirtualDriveChannels.VIRTUAL_DRIVE_STAT` | File/directory metadata |
| `volume` | *(local)* | Answered from cached `DeviceEntity.storage_*` — no TauSync round-trip |
| `read` | `VirtualDriveChannels.VIRTUAL_DRIVE_READ` | Write JSON header, read file bytes back |
| `create` | `VirtualDriveChannels.VIRTUAL_DRIVE_CREATE` | Create file or directory |
| `write_open` | `VirtualDriveChannels.VIRTUAL_DRIVE_WRITE` | Open write session; stream holds open until `write_close` |
| `write` / `write_close` | *(held open stream)* | Chunks forwarded; EOF on close signals Android to rename temp → final |
| `rename` | `VirtualDriveChannels.VIRTUAL_DRIVE_RENAME` | Move / rename |
| `truncate` | `VirtualDriveChannels.VIRTUAL_DRIVE_TRUNCATE` | Resize file |
| `delete` | `VirtualDriveChannels.VIRTUAL_DRIVE_DELETE` | Remove file or directory |

Started on `device_viewmodel.device_connected`; stopped (and `VirtualDrive.exe` terminated) on
`device_viewmodel.device_disconnected`. A watchdog thread restarts `VirtualDrive.exe` if it
crashes. A second watchdog closes write sessions open longer than 5 minutes.

| Signal | Payload | When |
|---|---|---|
| `drive_error` | `str` | Pipe-level error or VirtualDrive.exe crash |

### `PhoneRequestService`

Polls `tau.get_peer_waiting_words()` to detect channels the phone has opened before `SyncDose`
has called `connect()` on them. Routes each detected channel to a registered handler.

Default handler map (registered in `AppState`):

| Channel | Handler |
|---|---|
| `FileTransferChannels.REGULAR_FILE_METADATA_ANDROID_TO_PC` | `FileTransferService.receive_metadata` |
| `SessionChannels.DISCONNECT_FROM_PHONE` | `ConnectivityService.disconnect_device` |
| `BackupChannels.*` | `BackupService` (backup session control channel) |

### `ClipboardService`

Two-directional clipboard sync between the PC and Android over TauSync.

**Android → PC (manual):** `PhoneRequestService` detects Android waiting on `CLIPBOARD_ANDROID_TO_PC`
and calls `receive()`. A daemon thread reads the JSON payload, checks the SHA-256 hash to skip
duplicates, and emits `clipboard_text_received` so the main-thread slot in `MainWindow` calls
`QClipboard.setText()`.

**PC → Android (automatic):** `MainWindow` wires `QClipboard.dataChanged` to
`on_clipboard_changed()`. The method hashes the new content, skips if unchanged, updates
`_last_synced_hash`, and spawns a daemon thread that writes the JSON payload to
`CLIPBOARD_PC_TO_ANDROID`.

**Anti-loop guard:** `_last_synced_hash` (SHA-256) is set in `_receive()` *before* emitting the
signal, so the clipboard change that results from `setText()` is silently dropped by
`on_clipboard_changed`.

| Signal | Payload | When |
|---|---|---|
| `clipboard_text_received` | `str` | Text received from Android; connect to main-thread `QClipboard.setText()` |

| Channel | Wire value | Direction | Purpose |
|---|---|---|---|
| `CLIPBOARD_ANDROID_TO_PC` | `clipboard_android_to_pc` | Android → PC | User-initiated push |
| `CLIPBOARD_PC_TO_ANDROID` | `clipboard_pc_to_android` | PC → Android | Automatic push on PC clipboard change |

### `WebcamService`

Receives a live camera stream from Android and feeds it into a virtual webcam via `pyvirtualcam`.

Flow:
1. `PhoneRequestService` detects Android waiting on `webcam_start` and calls `receive_start()`.
2. A daemon thread connects to `WEBCAM_START` (reads the handshake), then opens `pyvirtualcam.Camera` at 1280×720 @ 24 fps.
3. The thread connects to `WEBCAM_FRAMES` and reads length-prefixed JPEG frames in a loop.
4. Each JPEG is decoded with Pillow, padded to 1280×720 preserving aspect ratio (`ImageOps.pad`), converted to a numpy array, and pushed to the virtual camera via `cam.send()`.
5. When Android closes the channel, `webcam_stopped` is emitted and the virtual camera is released.

| Signal | Payload | When |
|---|---|---|
| `webcam_started` | — | Virtual camera opened and streaming |
| `webcam_stopped` | — | Stream ended (normal or disconnected) |
| `webcam_error` | `str` | Unrecoverable exception in the stream loop |

**Prerequisite:** OBS Virtual Camera driver must be installed on the PC (`pyvirtualcam` uses it as its backend).

### `ToolService`

A thin wrapper around `ToolRepository`. Re-emits the repository's mutation signals at the service
boundary so ViewModels never need to import from `repositories/`.

| Signal | Payload | When |
|---|---|---|
| `tool_added` | `ToolEntity` | Forwarded from `ToolRepository.entity_saved` |
| `tool_deleted` | `str` (title) | Forwarded from `ToolRepository.entity_deleted` |
| `all_enabled_tools_fetched` | `list[ToolEntity]` | `fetch_all_enabled()` completes |

---

## ViewModels

ViewModels are `QObject` subclasses. They subscribe to service signals in `__init__`, convert
entities to DTOs, and expose their own signals for the view to bind to. They hold no network or
database state — that lives in services and repositories.

### `DeviceViewModel`

Drives both the login screen device list and the dashboard device cards.

| Signal | Payload | When |
|---|---|---|
| `device_infos_updated` | `list[DeviceInfoDTO]` | Current device data changed (refresh or new connect) |
| `previous_devices_updated` | `list[PreviousDeviceDTO]` | All historical devices loaded |
| `device_connected` | — | Forwarded from `ConnectivityService` |
| `device_disconnected` | — | Forwarded from `ConnectivityService` |

A `QTimer` fires every 10 minutes while connected to pull a fresh `DeviceEntity` from
`DeviceInfoService.fetch_device_info()`, keeping the dashboard cards up to date without
manual user action.

The ViewModel also seeds a mock `DeviceEntity` on construction so the dashboard renders
with placeholder data before any real phone connects.

### `FileTransferViewModel`

Gates all send/receive-metadata calls behind a connectivity flag. Operations started while
connected that complete or fail after a disconnect still surface their result (in-flight transfers
are not aborted).

| Signal | Payload | When |
|---|---|---|
| `send_complete` | `(str, int)` | File sent successfully |
| `send_error` | `str` | Send failed or rejected |
| `metadata_received` | `(str, int)` | Show accept/reject toast |
| `receive_complete` | `(str, str)` | File saved |
| `receive_error` | `str` | Receive failed |

`MainWindow` listens to `metadata_received` and shows a `FileReceivedToast`. The toast calls
back into the ViewModel via `receive_file(dest_path, size)` or `reject_receive()`.

### `ToolViewModel`

Drives the tools grid. Maintains an in-memory `list[ToolDTO]` of enabled tools.
On construction it calls `ToolService.start()` + `fetch_all_enabled()` so the grid is populated
asynchronously without blocking the UI thread.

| Signal | Payload | When |
|---|---|---|
| `tools_loaded` | `list[ToolDTO]` | `load_enabled_tools()` called |
| `tool_added` | `ToolDTO` | New tool saved |
| `tool_deleted` | `str` (title) | Tool removed |
| `tool_updated` | `str` (title) | Tool modified |
| `tool_count_changed` | `int` | Enabled count changed |

### `BackupViewModel`

Coordinates backup session state and surfaces the review queue to the UI. Subscribes to
`BackupService` signals and exposes them as view-ready signals so backup widgets never
import from `services/` directly.

| Signal | Payload | When |
|---|---|---|
| `backup_session_prompt` | `BackupSessionPromptDTO` | New backup session ready for user confirmation |
| `backup_review_prompt` | `list[BackupReviewPromptDTO]` | ML-flagged files ready for user decision |
| `backup_file_result` | `(str, BackupFileResult)` | Per-file verdict (drives progress window) |
| `backup_complete` | — | Session finished |
| `backup_error` | `str` | Session failed |

---

## Repositories

Both repositories use the same `IRepository[T, K]` interface from `repositories/repository.py`:

| Method | Description |
|---|---|
| `get_by_id(id: K) → T \| None` | Fetch a single entity by primary key |
| `get_all() → list[T]` | Fetch all entities |
| `save(entity: T) → None` | Insert or replace an entity (upsert via `REPLACE INTO`) |
| `delete(id: K) → None` | Remove an entity by primary key |

Both also emit `entity_saved: Signal` and `entity_deleted: Signal` after mutations.

Each method opens a short-lived `sqlite3` connection, making the repositories safe to call from
any thread simultaneously. The `ABCQObjectMeta` metaclass in `utils/meta.py` bridges Python's
`ABCMeta` with Qt's `type` so that the abstract base and `QObject` can be combined without a
metaclass conflict.

### `ToolRepository`

Adds `get_all_enabled()` → `list[ToolEntity]` (queries `WHERE is_enabled = 1`) and
`id_exists(title)` → `bool`.

Seeds the `tools` table with one default tool ("Send File to Phone") on first run using
`INSERT OR IGNORE`, so the seed is also applied to existing installs that pre-date it without
overwriting any user edits.

### `DeviceRepository`

Adds `id_exists(id)` → `bool`. Stores the full device history — every paired device is persisted
with its last-known battery, storage, IP, and timestamp.

---

## Serializers

Serializers convert between typed entities and raw SQLite row tuples. All implement
`ISerializer[T, K]` from `serializers/serializer.py`:

| Method | Description |
|---|---|
| `serialize(entity: T) → tuple \| None` | Entity → positional tuple for a parameterized `INSERT`/`REPLACE` |
| `deserialize(row: tuple) → T \| None` | Row tuple → entity; returns `None` for `None` or empty input |

### `DeviceSerializer`

Maps `DeviceEntity ↔ (id, name, os, tag, last_connected, battery_level, battery_charging, storage_used, storage_total, ip)`.
`last_connected` is coerced between `datetime.date` and an ISO string (`%Y-%m-%d`) at the boundary.

### `ToolSerializer`

Maps `ToolEntity ↔ (title, description, icon_path, is_enabled)`.

### `FileMetadataSerializer`

Converts `FileMetadataDTO ↔ JSON string`. Used by `FileTransferService` to transmit file name
and size over the `file_meta` TauSync channel before the raw bytes are sent.

### `BackupSessionSerializer`

Converts `BackupSessionPromptDTO ↔ JSON string`. Used by `BackupService` to parse the session
manifest sent by the Android app at the start of a backup session.

---

## Database

Both repositories share a single SQLite file at:

```
%APPDATA%\SyncDose\app.db
```

(`Path(os.environ["APPDATA"]) / "SyncDose" / "app.db"`)

The directory and file are created automatically on first run. There is no migration tooling —
both repositories call `CREATE TABLE IF NOT EXISTS` on construction.

To reset to factory state: delete `%APPDATA%\SyncDose\app.db` and relaunch.

### Schema

**`devices` table** (managed by `DeviceRepository`):

| Column | Type | Notes |
|---|---|---|
| `id` | `TEXT PRIMARY KEY` | UUID; assigned by SyncDose if the phone has none |
| `name` | `TEXT` | Human-readable device name |
| `os` | `TEXT` | OS version string (e.g. `"Android 14"`) |
| `tag` | `TEXT` | User label; defaults to `"default"` |
| `last_connected` | `DATETIME` | ISO date string (`%Y-%m-%d`) |
| `battery_level` | `INTEGER` | 0–100 |
| `battery_charging` | `BOOLEAN` | `1` = charging |
| `storage_used` | `INTEGER` | Bytes used |
| `storage_total` | `INTEGER` | Total bytes |
| `ip` | `TEXT` | Last known IP address |

**`tools` table** (managed by `ToolRepository`):

| Column | Type | Notes |
|---|---|---|
| `title` | `TEXT PRIMARY KEY` | Tool name; used as the display label and primary key |
| `description` | `TEXT` | Short description on the tool card |
| `icon_path` | `TEXT` | Qt virtual filesystem path (e.g. `":/icons/android.svg"`) |
| `is_enabled` | `BOOLEAN` | `1` = shown in the tools grid |

---

## File Transfer & IPC

File transfer involves two independent flows:

### Flow 1 — Send from SyncDose dashboard

1. User selects a file in the SyncDose dashboard → `FileTransferViewModel.send_file(path)` →
   `FileTransferService.send_file(path)` on a background thread.
2. Metadata (name + size as JSON) is sent over `FileTransferChannels.REGULAR_FILE_METADATA_PC_TO_ANDROID`.
3. Service waits for accept/reject on `FileTransferChannels.REGULAR_FILE_RESPONSE_FROM_ANDROID`.
4. If accepted: raw bytes are streamed over `FileTransferChannels.REGULAR_FILE_DATA_PC_TO_ANDROID`
   using `stream.write_file()` (constant memory, any file size).

### Flow 2 — Send via Windows shell "Send with SyncDose"

`FileHandler.exe` is registered in the Windows shell as a context-menu handler for
"Send with SyncDose". When the user right-clicks a file and selects it:

1. The OS launches `FileHandler.exe` (`core/file_handler.py`) with the file path as an argument.
2. `FileHandler.exe` connects to the named pipe `\\.\pipe\FileSend` (served by `SyncDose.exe`)
   and writes the file path, then exits.
3. `SyncDose.exe` reads the path from the pipe inside `FileTransferService._listen_for_file_to_send()`
   (which loops on `Server.wait_for_client()`) and calls `send_file(path)`.

The named pipe IPC is implemented in `desktop/native/windows/pipe/` — a C++ pybind11 module that
exposes `Server` and `Client` classes.

### Flow 3 — Receive from phone

The phone initiates the transfer. `PhoneRequestService` detects the phone's waiting channel
(`FileTransferChannels.REGULAR_FILE_METADATA_ANDROID_TO_PC`) and calls
`FileTransferService.receive_metadata()`:

1. Metadata is received and `FileTransferService.file_metadata_received` is emitted.
2. `FileTransferViewModel` forwards this to `MainWindow` via its own `metadata_received` signal.
3. `MainWindow` shows a `FileReceivedToast` with the filename and size.
4. User clicks **Save** → toast calls `FileTransferViewModel.receive_file(dest_path, size)` →
   service writes accept token and streams bytes to disk via `stream.read_to_file()`.
5. User clicks **Cancel** → toast calls `FileTransferViewModel.reject_receive()` →
   service writes reject token; sender aborts.

---

## Qt Resources

Icons and QSS stylesheets are embedded in the compiled `resources_qrc.py` module and accessed
through Qt's virtual filesystem. All virtual paths are declared as typed `StrEnum` members in
`resources/paths.py`.

**Adding a new asset:**

1. Place the file in `resources/icons/` or `resources/styles/`
2. Register it in `resources/syncdose.qrc`
3. Add a `StrEnum` entry in the correct class in `resources/paths.py`
4. Recompile: `pyside6-rcc resources/syncdose.qrc -o resources_qrc.py`
5. Commit `resources_qrc.py` — it must be up to date in version control

**Loading QSS in a widget:**

```python
from utils.styles import load_stylesheet, themed
from resources.colors import Colors, LightColors
from resources.paths import DashboardStyles
from app.theme_manager import theme_manager

def _setup_style(self) -> None:
    self.setStyleSheet(
        load_stylesheet(
            DashboardStyles.INFO_CARD,
            themed([Colors], [LightColors], theme_manager.is_dark),
        )
    )
```

`load_stylesheet(path, substitutions)` reads the QSS file from the virtual filesystem and applies
`str.format_map(substitutions)` to replace `{TOKEN_NAME}` placeholders with actual hex values.
`themed(dark_enums, light_enums, is_dark)` merges the appropriate color enum members into a single
substitution dict, so the same QSS template works for both themes.

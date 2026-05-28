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
- **Sidebar Navigation** — Icon-based sidebar with logo; `NavigationManager` drives all
  screen transitions without coupling widgets to `MainWindow`

---

## Requirements

| Dependency        | Version   | Notes |
|-------------------|-----------|-------|
| Python            | 3.13      | f-strings, `match`, and type-union syntax (`A \| B`) are used |
| PySide6           | ≥ 6.5.0   | Qt bindings — included in `requirements.txt` |
| pythonnet         | ≥ 3.0.0   | CLR bridge for TauSync .NET calls — installed as a `tausync_py` dependency |
| tausync_py        | local pkg  | TauSync Python wrapper — requires the `.dll` (see setup) |
| qrcode[pil]       | ≥ 7.4.2   | QR image generation for the login panel |
| pytest            | ≥ 8.3.4   | Dev only — test runner |
| pytest-qt         | ≥ 4.4.0   | Dev only — `QApplication` fixtures for ViewModel/widget tests |
| pyinstaller       | ≥ 5.11.0  | Dev only — needed to produce standalone `.exe` files |

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

The production install is two separate PyInstaller executables bundled into a single MSI:

```powershell
# Build both executables (resources must already be compiled)
pyinstaller desktop/installer/specs/main_app.spec      # → SyncDose.exe
pyinstaller desktop/installer/specs/file_handler.spec  # → FileHandler.exe

# Package as MSI using WiX
dotnet build desktop/installer/ -c Release
```

The MSI is uploaded as an artifact by CI (`desktop.yml` → `build` job). See the
[CI/CD section in the root README](../README.md#cicd) for the full pipeline.

**Why two executables?**

`SyncDose.exe` runs as the main dashboard. `FileHandler.exe` is a tiny helper registered as the
Windows shell "Send with SyncDose" right-click handler — it receives the target file path via the
OS, writes it to a named pipe (`\\.\pipe\FileSend`), and exits. `SyncDose.exe` reads that path
from the pipe and initiates the file send to the connected phone. See [File Transfer & IPC](#file-transfer--ipc).

---

## Project Structure

```
desktop/
│
├── run.py                          # Dev launcher: compile resources → run tests → start app
├── main.py                         # Entry point: QApplication + deferred imports + MainWindow
├── requirements.txt                # Runtime + dev deps (PySide6, pytest, pytest-qt, qrcode…)
├── resources_qrc.py                # AUTO-GENERATED by pyside6-rcc — do not edit
│
├── app/                            # Application-level singletons (not domain logic)
│   ├── app_state.py                # AppState — the single DI root (see Architecture)
│   ├── navigation_manager.py       # NavigationManager singleton + navigate(int) Signal
│   └── theme_manager.py            # ThemeManager singleton — tracks Windows dark/light scheme
│
├── core/
│   └── pipe_client.py              # Entry point for FileHandler.exe — writes path to named pipe
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
│       └── session_channels.py     # SessionChannels — DISCONNECT_FROM_PHONE, DISCONNECT_FROM_PC
│
├── native/
│   └── windows/
│       └── pipe/                   # C++ pybind11 named-pipe module (Server / Client classes)
│
├── repositories/                   # Data-access layer — SQLite via sqlite3
│   ├── repository.py               # IRepository[T, K] abstract base (get_by_id, get_all, save, delete)
│   ├── device.py                   # DeviceRepository — devices table; emits entity_saved / entity_deleted
│   └── tool.py                     # ToolRepository — tools table; seeds 10 defaults on first run
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
├── serializers/                    # Convert entities ↔ SQLite row tuples
│   ├── serializer.py               # ISerializer[T, K] abstract base (serialize / deserialize)
│   ├── device.py                   # DeviceSerializer — DeviceEntity ↔ 10-column row tuple
│   ├── file_metadata.py            # FileMetadataSerializer — FileMetadataDTO ↔ JSON string
│   └── tool.py                     # ToolSerializer — ToolEntity ↔ 4-column row tuple
│
├── services/                       # Background services — all I/O on daemon threads, never QThread
│   ├── connectivity.py             # ConnectivityService — TauSync TCP lifecycle
│   ├── device_info.py              # DeviceInfoService — reads device channels, persists entity
│   ├── file_transfer.py            # FileTransferService — send/receive files + named-pipe listener
│   ├── phone_request.py            # PhoneRequestService — polls peer waiting channels, dispatches
│   └── tool.py                     # ToolService — wraps ToolRepository, re-emits its signals
│
├── utils/                          # Shared utilities (no singletons here)
│   ├── meta.py                     # ABCQObjectMeta — metaclass bridging ABC and QObject
│   ├── network.py                  # get_ip_by_hostname(), read_string_from_channel()
│   └── styles.py                   # load_stylesheet(), themed() — QSS loading helpers
│
├── viewmodels/                     # PySide6 QObject ViewModels — DTOs + Signals
│   ├── device.py                   # DeviceViewModel — drives login list + dashboard device cards
│   ├── file_transfer.py            # FileTransferViewModel — gates send/receive behind connectivity
│   └── tool.py                     # ToolViewModel — drives the tools grid
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
│       ├── toasts/
│       │   └── file_received.py        # FileReceivedToast — accept/reject prompt for incoming file
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
    │   ├── test_file_transfer.py
    │   └── test_phone_request.py
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
        self.phone_request_service  = PhoneRequestService(connectivity, file_transfer_service)

        # ViewModels
        self.device_viewmodel        = DeviceViewModel(connectivity_service, device_info_service)
        self.file_transfer_viewmodel = FileTransferViewModel(file_transfer_service, connectivity_service)
        self.tool_viewmodel          = ToolViewModel(tool_service)

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

Manages the TauSync TCP connection lifecycle. Listens for incoming connections in server mode
(default) or connects to a device by IP in client mode.

| Signal | Payload | When |
|---|---|---|
| `device_connected` | — | `listen()` returns a client, or `connect_to_device()` succeeds |
| `device_disconnected` | — | `disconnect_device()` disposes the connection |
| `connection_error` | `str` | `listen()` raises an unexpected exception |

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

### `PhoneRequestService`

Polls `tau.get_peer_waiting_words()` to detect channels the phone has opened before `SyncDose`
has called `connect()` on them. Routes each detected channel to a registered handler.

Default handler map (registered in `AppState`):

| Channel | Handler |
|---|---|
| `FileTransferChannels.REGULAR_FILE_METADATA_ANDROID_TO_PC` | `FileTransferService.receive_metadata` |
| `SessionChannels.DISCONNECT_FROM_PHONE` | `ConnectivityService.disconnect_device` |

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

Seeds the `tools` table with 10 placeholder tools on the first run (when the table is empty).
Tools 1, 2, 3, 4, 6, 8, 10 seed as enabled; Tools 5, 7, 9 seed as disabled.

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

1. The OS launches `FileHandler.exe` (`core/pipe_client.py`) with the file path as an argument.
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

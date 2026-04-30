# SyncDose — Windows Client

A desktop dashboard application for monitoring and managing connected Android devices on Windows. Built with Python and
PySide6, SyncDose provides a clean, real-time view of device status including battery, storage, connection state, and a
configurable tools grid.

---

## Table of Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Development Installation](#development-installation)
4. [Production Installation](#production-installation)
5. [Running the App](#running-the-app)
6. [Running Tests](#running-tests)
7. [Development vs Production](#development-vs-production)
8. [Production Build](#production-build)
9. [Project Structure](#project-structure)
10. [Architecture](#architecture)
11. [Screen Navigation](#screen-navigation)
12. [Login Screen](#login-screen)
13. [Services](#services)
14. [Serializers](#serializers)
15. [Database](#database)
16. [Repository Interfaces](#repository-interfaces)
17. [Configuration](#configuration)

---

## Features

- 📱 **Device Dashboard** — View connected device name, type, battery level, charging status, and storage usage at a
  glance
- 🔌 **Connection Status** — Live connection indicator with a pulsing dot and connection pill widget
- 🛠️ **Tools Grid** — Configurable grid of action tools backed by `data/app.db`, with enabled/disabled states
- 🔑 **Login Screen** — QR code pairing panel + scrollable list of previously connected devices with hover-to-connect
  cards
- 🧭 **Sidebar Navigation** — Icon-based sidebar with logo and navigation items
- 🎨 **Custom Theming** — QSS stylesheets per component under `resources/styles/`, with a centralized color palette
- 🔔 **System Tray** — Minimize-to-tray on close; restore via double-click or right-click context menu

---

## Requirements

| Dependency  | Version  | Notes                                                                        |
|-------------|----------|------------------------------------------------------------------------------|
| Python      | 3.10+    | f-strings and `match` statements are used throughout                         |
| PySide6     | ≥ 6.5.0  | Qt bindings — included in `requirements.txt`                                 |
| pythonnet   | ≥ 3.0.0  | CLR bridge for TauSync .NET calls — installed as a `tausync-py` dependency   |
| tausync-py  | ≥ 0.1.0  | TauSync Python wrapper — requires building the `.dll` first (see below)      |
| qrcode[pil] | ≥ 7.4.2  | QR image generation for the login panel                                      |
| pytest      | ≥ 8.3.4  | Dev only — test runner                                                       |
| pytest-qt   | ≥ 4.4.0  | Dev only — Qt application fixtures for unit tests                            |
| pyinstaller | ≥ 5.11.0 | Dev only — only needed to produce a standalone `.exe` via `production.spec`  |

---

## Installation

> **Which path do you need?**
> - **[Development](#development-installation)** — running or modifying the source code on your machine
> - **[Production](#production-installation)** — deploying the built `.exe` on a target Windows machine

---

## Development Installation

### 1. Clone the repository

```bash
git clone <repo-url>
cd Ecosystem
```

### 2. Create and activate a virtual environment

A virtual environment is strongly recommended — `pythonnet` (TauSync's CLR bridge) conflicts with other packages
if installed globally.

```bash
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Windows (cmd)
python -m venv .venv
.venv\Scripts\activate.bat
```

### 3. Build the TauSync DLL

`tausync-py` wraps a compiled .NET 8 assembly. You must build the `.dll` before installing the Python package.
Run Docker Compose from the **`TauSync/`** directory:

```bash
cd TauSync/
docker compose up
```

This compiles `TauSync.Lib.csproj` inside a `mcr.microsoft.com/dotnet/sdk:8.0` container and writes the output
directly to `TauSync/windows/tausync_py/dll/`. Docker is the only prerequisite — no local .NET SDK needed.

> **Without Docker:** If Docker is unavailable, install the [.NET 8 SDK](https://dotnet.microsoft.com/download)
> and run:
> ```bash
> cd TauSync/Tausync_Windows/TauSync.Lib/
> dotnet publish -c Release -o ../../../windows/tausync_py/dll/
> ```

After a successful build:
```
TauSync/windows/tausync_py/dll/
├── TauSync.Lib.dll        ← loaded by pythonnet at runtime
├── TauSync.Lib.deps.json
└── TauSync.Lib.pdb
```

### 4. Install all Python dependencies

```bash
cd desktop/
pip install -r requirements.txt
```

This installs: `PySide6`, `pytest`, `pytest-qt`, `qrcode[pil]`, `pyinstaller`, and `tausync-py`
(including `pythonnet` as its dependency). The `tausync-py` package bundles the DLL you built in Step 3
automatically via its `package-data` declaration.

### 5. Compile Qt resources

Icons and QSS stylesheets are accessed through Qt's virtual filesystem and must be compiled into
`resources_qrc.py` before the app can run. `run.py` does this automatically, but to do it manually:

```bash
pyside6-rcc resources/syncdose.qrc -o resources_qrc.py
```

`resources_qrc.py` is auto-generated — do not edit it by hand. Re-run this command whenever you add a new
icon or stylesheet, and commit the updated file.

### 6. Verify

```bash
python -c "from PySide6.QtWidgets import QApplication; print('PySide6 OK')"
python -c "from tausync_py import TauSync; print('TauSync OK')"
```

### Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `pyside6-rcc: command not found` | PySide6 not installed or venv not active | Activate the venv and re-run `pip install -r requirements.txt` |
| `ModuleNotFoundError: resources_qrc` | Resources not compiled | Run `pyside6-rcc resources/syncdose.qrc -o resources_qrc.py` |
| `FileNotFoundError: TauSync.Lib.dll not found` | DLL not built yet | Complete Step 3 — `docker compose up` from `TauSync/` |
| `0xC0000409` fatal crash | TauSync called from a `QThread` | Never run TauSync blocking calls from a Qt-managed thread — use `threading.Thread` |
| Qt window is blank / unstyled | `resources_qrc.py` stale or missing | Delete `resources_qrc.py` and recompile |
| `pytest` not found | Dev deps not installed | Run `pip install -r requirements.txt` inside the venv |

---

## Production Installation

The production build is a self-contained folder — no Python, no pip, no resource compilation needed on the
target machine.

### On the build machine (developer)

Follow the [Production Build](#production-build) section to produce `desktop/dist/SyncDose/`. This requires
Docker and takes about 2–5 minutes on first run.

### On the target machine (end user)

**Step 1 — Install the .NET 8 Runtime**

TauSync uses `pythonnet` to call into the .NET assembly at runtime. The .NET runtime is **not** bundled by
PyInstaller and must be installed on the target machine:

- Download: [https://dotnet.microsoft.com/download/dotnet/8.0](https://dotnet.microsoft.com/download/dotnet/8.0)
- Install the **.NET 8 Runtime** (not the SDK) — the "Run apps" variant is sufficient

**Step 2 — Copy the build output**

Copy the entire `dist/SyncDose/` folder to any location on the target machine:

```
SyncDose/             ← copy this whole folder
├── SyncDose.exe
├── data/             ← app.db is created here on first launch
├── resources/
└── _internal/
```

There is no installer. The folder is self-contained — place it wherever you like (e.g. `C:\Program Files\SyncDose\`).

**Step 3 — Run**

Double-click `SyncDose.exe` or launch it from a terminal. On first launch:
- `data/app.db` is created automatically
- Default tools are seeded into the database
- Nothing else needs to be configured

### Production troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `FileNotFoundError: TauSync.Lib.dll not found` | DLL missing from `_internal/` | Rebuild the exe — the DLL must be present before PyInstaller runs |
| App crashes on start with a CLR error | .NET 8 Runtime not installed | Install .NET 8 Runtime from microsoft.com/dotnet |
| Window opens but is unstyled | `resources/` folder missing or moved | Ensure the entire `SyncDose/` folder was copied, not just `SyncDose.exe` |
| `data/app.db` grows unexpectedly | Normal — devices write on every connect | Safe to delete; it is recreated on next launch |

---

## Running the App

### Standard launch (compiles resources + runs all tests, then starts)

```bash
python run.py
```

`run.py` always executes three steps in order:

1. **Compile resources** — runs `pyside6-rcc resources/syncdose.qrc -o resources_qrc.py`
2. **Run all unit tests** — runs `pytest unit_tests/ -v`; aborts if any test fails
3. **Launch the app** — spawns `python main.py`

If any test fails, the app will not launch. Fix the failing tests before proceeding.

### Direct launch (skip resource compilation and tests)

```bash
python main.py
```

Use this only when you are certain the resources are already compiled and you want a faster iteration loop. This is
the mode used by `run.py` internally after it has completed the compile and test steps.

The dashboard window opens at **1100 × 720**. Closing the window minimizes it to the system tray. Right-click the
tray icon and select **Quit** to exit, or double-click the icon to restore the window.

---

## Running Tests

```bash
pytest unit_tests/
```

Tests cover repositories, serializers, stores, services, and view-models. Shared fixtures (mock stores, mock
serializers, in-memory repositories) are defined in `unit_tests/conftest.py`.

Run a single test module:

```bash
pytest unit_tests/repositories/test_tool.py -v
```

Run with coverage (requires `pytest-cov`):

```bash
pytest unit_tests/ --cov=. --cov-report=term-missing
```

> `pytest-qt` is required even for tests that do not open windows — several viewmodel tests instantiate `QObject`
> subclasses, which require a running `QApplication`. The `pytest-qt` plugin provides the `qtapp` fixture that
> satisfies this automatically.

---

## Development vs Production

| Concern | Development | Production |
|---|---|---|
| Entry point | `python run.py` or `python main.py` | `dist/SyncDose/SyncDose.exe` |
| Resource compilation | `pyside6-rcc` run by `run.py` or manually | Must be run **before** `docker run` |
| Tests | Always run by `run.py` before launch | Not run during the build |
| `tausync-py` source | Installed from `requirements.txt` | Installed from the local build mounted at `/windows` |
| Build tool | None — runs from source | PyInstaller via Docker |
| Data directory | `desktop/data/app.db` (local) | Bundled inside `dist/SyncDose/data/` |
| Deps in image | Only `requirements.txt` + the local `tausync_py` package | Same — PySide6 comes from `requirements.txt` |

---

## Production Build

The production executable is a self-contained folder (`dist/SyncDose/`) built with **PyInstaller** inside a
**Docker container**. Docker is used to guarantee a clean, reproducible Windows-targetable build environment —
no stray local packages or path leakage.

### Prerequisites

1. **Docker** installed and running
2. `tausync-py` **already compiled** — the build mounts `TauSync/windows/` (the Python package source) into the
   container as a volume. Build that package first if you haven't:
   ```bash
   cd TauSync/windows && pip install build && python -m build
   ```
3. **Qt resources compiled** — run this once before building so `resources_qrc.py` exists:
   ```bash
   cd desktop && pyside6-rcc resources/syncdose.qrc -o resources_qrc.py
   ```

### Build steps

```bash
# 1. Build the Docker image (run from the desktop/ directory)
cd desktop
docker build -t syncdose-builder .

# 2. Run the container, mounting the tausync_py package source
#    The /windows volume maps to TauSync/windows/ — make_exe.sh installs it with pip install /windows
docker run --rm \
  -v "$(pwd)/dist:/app/dist" \
  -v "$(pwd)/../TauSync/windows:/windows" \
  syncdose-builder
```

> **Windows PowerShell:** replace `$(pwd)` with `${PWD}`.

### What the container does

`make_exe.sh` (the container's CMD) executes three steps:

1. `pip install /windows` — installs `tausync-py` from the mounted local source
2. `pip install -r requirements.txt` — installs all other dependencies
3. `pyinstaller production.spec` — packages the app

### Output

```
desktop/
└── dist/
    └── SyncDose/           # Copy this entire folder to the target machine
        ├── SyncDose.exe    # Main executable
        ├── data/           # Bundled database directory (app.db created on first launch)
        ├── resources/      # Bundled icons and QSS stylesheets
        └── _internal/      # PyInstaller runtime, compiled Python modules
```

The `dist/SyncDose/` folder is self-contained — copy it to the target Windows machine and run `SyncDose.exe`.
No Python installation is required on the target.

> **`app.db` on first launch:** The bundled `data/` directory may be empty. `DeviceRepository` and
> `ToolRepository` create `app.db` and their tables automatically on first run. Default tools are seeded
> on the same run. Nothing needs to be done manually.

### Key differences from development

- **No tests** — `run.py` (which calls pytest) is not used. PyInstaller packages `main.py` directly.
- **No `pyside6-rcc` inside the container** — `resources_qrc.py` must exist before `docker build`, because
  the `.dockerignore` excludes `dist/` and build artifacts but not `resources_qrc.py`.
- **UPX compression** — `production.spec` enables UPX (`upx=True`) to reduce the bundle size. If UPX is not
  installed in the container, PyInstaller falls back to uncompressed silently.
- **Console window** — `console=True` in the spec means a terminal window is visible alongside the app.
  Set `console=False` for a window-only build (no stdout).

---

## Project Structure

```
desktop/
│
├── run.py                        # Dev launcher — compiles resources, runs tests, then starts the app
├── main.py                       # Entry point — bootstraps QApplication and MainWindow
├── requirements.txt              # Runtime + dev dependencies (PySide6 installed separately)
├── resources_qrc.py              # AUTO-GENERATED — compiled Qt resource module; do not edit
│
├── Dockerfile                    # Production build image — runs make_exe.sh inside a clean container
├── .dockerignore                 # Excludes venv, dist, build, and compiled artifacts from the image
├── make_exe.sh                   # Build script run inside the container: installs deps → PyInstaller
├── production.spec               # PyInstaller spec — bundles main.py + data/ + resources/ into SyncDose.exe
│
├── data/
│   └── app.db                    # SQLite database — created automatically on first launch
│
├── dto/                          # Data Transfer Objects — lightweight dicts passed from ViewModels to Views
│   ├── device_info.py            # DeviceInfoDTO
│   ├── previous_device.py        # PreviousDeviceDTO
│   └── tool.py                   # ToolDTO
│
├── entities/                     # Domain entities — typed dataclasses; the canonical data model
│   ├── device_info.py            # DeviceEntity (id, name, os, battery, storage, ip, last_connected, tag)
│   └── tool.py                   # ToolEntity (title, description, icon_path, icon_bg_color, is_enabled)
│
├── enums/                        # Typed enumerations used across all layers
│   ├── channel.py                # Channel — TauSync named channel identifiers
│   ├── device_info_channels.py   # DeviceInfoChannels — per-field TauSync channel IDs for device info
│   ├── device_status.py          # DeviceStatus StrEnum (ONLINE, RECENT, IDLE) — login card badge states
│   ├── device_type.py            # DeviceType enum (DEVICE_NAME, DEVICE_TYPE, BATTERY, STORAGE)
│   └── screen.py                 # Screen IntEnum (LOGIN = 0, DASHBOARD = 1) — NavigationManager indices
│
├── layouts/
│   └── flow_layout.py            # FlowLayout — custom Qt layout that wraps children like inline text
│
├── repositories/                 # Data-access layer — SQLite-backed; emit PySide6 signals on mutation
│   ├── interfaces/
│   │   └── base.py               # IRepository[T, K] — generic abstract base (get_by_id, get_all, save, delete)
│   ├── device.py                 # DeviceRepository — devices table in app.db; emits entity_saved / entity_deleted
│   └── tool.py                   # ToolRepository — tools table in app.db; seeds defaults on first run
│
├── resources/                    # Design tokens and Qt virtual filesystem paths
│   ├── colors.py                 # Two-layer color system: Palette (raw hex) → Colors (semantic roles)
│   ├── spacing.py                # Spacing scale constants: XS=4 · SM=8 · MD=12 · LG=16 · XL=20 · XXL=24 (px)
│   ├── paths.py                  # StrEnum paths into Qt virtual filesystem for icons and stylesheets:
│   │                             #   Icons, Styles, NavigationStyles, DashboardStyles,
│   │                             #   LoginStyles, IndicatorStyles
│   ├── syncdose.qrc              # Qt resource manifest — lists every icon and QSS file to embed
│   ├── icons/                    # SVG icons (logo, battery, storage, disconnect, refresh, dashboard, settings, …)
│   └── styles/                   # Per-component QSS stylesheets — mirrors the views/ widget tree
│       ├── dashboard/
│       │   ├── battery_info.qss
│       │   ├── content.qss
│       │   ├── device_status_row.qss
│       │   ├── info_card.qss
│       │   ├── storage_info.qss
│       │   ├── tool_card.qss
│       │   ├── tools_grid.qss
│       │   └── tools_section_header.qss
│       ├── indicators/
│       │   └── connection_pill.qss
│       ├── login/
│       │   └── left-panel.qss
│       ├── navigation/
│       │   ├── container.qss
│       │   ├── item.qss
│       │   └── sidebar.qss
│       ├── divider.qss
│       ├── logo_widget.qss
│       ├── section_label.qss
│       ├── topbar.qss
│       └── tray-menu.qss
│
├── serializers/                  # Convert entities ↔ SQLite row tuples for parameterized queries
│   ├── interfaces/
│   │   └── base.py               # ISerializer[T, K] — serialize() and deserialize() contract
│   ├── device.py                 # DeviceSerializer — maps DeviceEntity ↔ 10-column row tuple
│   └── tool.py                   # ToolSerializer — maps ToolEntity ↔ 4-column row tuple
│
├── services/                     # Background services — run off the UI thread
│   └── connectivity.py           # ConnectivityService — TauSync TCP lifecycle on a threading.Thread
│
├── stores/                       # DEPRECATED — no longer used by any active repository
│   └── interfaces/
│       └── base.py               # IStore[T, K] — load() and save() contract (retained for reference)
│
├── utils/                        # Application-wide singletons and helpers
│   ├── repository_manger.py      # RepositoryManager singleton — DI root for all repositories
│   ├── services_manager.py       # ServicesManager singleton — DI root for all services
│   ├── viewmodel_manager.py      # ViewModelManager singleton — DI root for all viewmodels
│   ├── navigation_manager.py     # NavigationManager singleton — emits navigate(Screen) signals
│   ├── network.py                # get_ip() and read_from_channel() — network utilities
│   ├── navigation_stack.py       # NavigationStack — push/pop history (reserved for future use)
│   ├── styles.py                 # load_stylesheet() — loads a QSS file from the Qt virtual filesystem
│   └── meta.py                   # ABCQObjectMeta — metaclass bridging ABC and QObject
│
├── viewmodels/                   # PySide6 QObject ViewModels — convert entities to DTOs, expose Signals
│   ├── device.py                 # DeviceViewModel — wraps DeviceRepository + ConnectivityService
│   └── tool.py                   # ToolViewModel — wraps ToolRepository
│
├── views/
│   ├── screens/
│   │   ├── login.py              # LoginScreen — LeftPanel + RightPanel in a 5 : 6 stretch ratio
│   │   └── dashboard.py          # DashboardScreen — Sidebar + Topbar + DashboardContent
│   └── widgets/
│       ├── dashboard/
│       │   ├── battery_info.py       # BatteryInfo — circular battery gauge with charging indicator
│       │   ├── dashboard_content.py  # DashboardContent — assembles the full dashboard content area
│       │   ├── info_card.py          # InfoCard — generic stat card (icon + label + value)
│       │   ├── phone_details_row.py  # PhoneDetailsRow — device name, OS, tag row at the top of dashboard
│       │   ├── storage_info.py       # StorageInfo — storage bar with used / total labels
│       │   ├── tool_card.py          # ToolCard — single tool tile in the tools grid
│       │   ├── tools_grid.py         # ToolsGrid — FlowLayout container for all ToolCard widgets
│       │   └── tools_section_header.py # ToolsSectionHeader — "Tools" section title + subtitle
│       ├── indicators/
│       │   ├── connection_pill.py    # ConnectionPill — pill badge showing CONNECTED / DISCONNECTED
│       │   ├── pill_wraper.py        # PillWrapper — layout host for ConnectionPill
│       │   └── pulsing_dot.py        # PulsingDot — animated dot (used in "Waiting…" indicator)
│       ├── login/
│       │   ├── left_panel.py         # LeftPanel — QR code, refresh button, pulsing-dot indicator
│       │   ├── previous_device_card.py # PreviousDeviceCard — hover-to-connect device list entry
│       │   ├── qr.py                 # QR — renders a QR code image with rounded corners
│       │   └── right_panel.py        # RightPanel — scrollable list of previously connected devices
│       ├── navigation/
│       │   ├── container.py          # NavigationContainer — sidebar + main content area wrapper
│       │   ├── item.py               # NavigationItem — single icon-based nav item
│       │   └── sidebar.py            # Sidebar — vertical strip of NavigationItems + logo
│       ├── bar.py                    # Bar — generic horizontal separator bar
│       ├── divider.py                # Divider — thin horizontal rule between sections
│       ├── logo_widget.py            # LogoWidget — app logo rendered from SVG
│       └── topbar.py                 # Topbar — top bar housing ConnectionPill and device status
│
├── unit_tests/
│   ├── conftest.py               # Shared pytest fixtures (mock stores, serializers, in-memory repos)
│   ├── repositories/
│   │   ├── test_device.py
│   │   └── test_tool.py
│   ├── serializers/
│   │   ├── test_device_info.py
│   │   ├── test_previous_device.py
│   │   └── test_tool.py
│   ├── services/
│   │   └── test_connectivity.py
│   ├── stores/
│   │   ├── test_device_info.py
│   │   ├── test_previous_device.py
│   │   └── test_tool.py
│   ├── utils/
│   │   ├── test_network.py
│   │   ├── test_repository_manager.py
│   │   ├── test_services_manager.py
│   │   └── test_styles.py
│   └── view_model/
│       ├── test_device_info.py
│       ├── test_previous_device.py
│       └── test_tool.py
│
└── windows/
    └── main_window.py            # MainWindow — QStackedWidget screen manager + system tray
```

---

## Architecture

SyncDose follows an **MVVM (Model-View-ViewModel)** pattern. Persistence is handled by repositories that talk
directly to a **SQLite database** (`data/app.db`) — there is no intermediate Store layer:

```
Views
  └─ bind to ──► ViewModels (DTOs + Signals)
                   └─ consume ──► Repositories (entities + Signals)
                                    └─ read/write ──► SQLite (data/app.db via sqlite3)
                                                         └─ use ──► Serializers (entity ↔ row tuple)
```

- **Entities** are plain Python dataclasses — the canonical domain model (`entities/`)
- **Serializers** map between typed entities and SQLite row tuples for parameterized queries (`serializers/`)
- **Repositories** own all database access — they create their tables on first use, seed default rows if the
  table is empty, and emit PySide6 `Signal`s on every mutation (`repositories/`)
- **ViewModels** convert entities to lightweight DTOs and re-emit signals that views bind to (`viewmodels/`)
- **Views** are PySide6 widgets — they connect to ViewModel signals and update the UI reactively (`views/`)

> **Note on the Stores layer:** `stores/interfaces/base.py` is retained in the repository for reference but
> no active repository uses the `IStore` interface — both repositories open `sqlite3` connections directly.

### Layer boundaries

| Layer        | May import from              | Must NOT import from            |
|--------------|------------------------------|---------------------------------|
| Views        | ViewModels, DTOs, resources  | Repositories, Entities directly |
| ViewModels   | Repositories, Entities, DTOs | Views                           |
| Repositories | Serializers, Entities        | Views, ViewModels               |

Violating these boundaries breaks testability — repositories cannot be mocked if views import them directly.

### DI singletons

All singletons are module-level instances constructed once at import time and imported wherever needed.

| Singleton            | Module                        | Holds                                    |
|----------------------|-------------------------------|------------------------------------------|
| `repository_manager` | `utils/repository_manger.py`  | `tools_repository`, `device_repository`  |
| `services_manager`   | `utils/services_manager.py`   | `connectivity_service`                   |
| `viewmodel_manager`  | `utils/viewmodel_manager.py`  | `device_viewmodel`                       |
| `navigation_manager` | `utils/navigation_manager.py` | `navigate` signal (emits `Screen` value) |

**Dependency direction:** `viewmodel_manager` → `repository_manager` + `services_manager` → (no further singletons).
`NavigationManager` is independent — any layer may call `navigation_manager.go_to_screen(Screen.X)` to trigger a
screen change without knowing anything about `MainWindow`.

### Design tokens

Never hardcode colors or spacing values in widget code. Use the centralized token files:

- **`resources/colors.py`** — Two-layer system: `Palette` (raw hex values) → `Colors` (semantic role names such as
  `PRIMARY`, `SURFACE`, `ON_SURFACE_MUTED`). Always reference `Colors.X`, never `Palette.X` directly in widgets.
- **`resources/spacing.py`** — A fixed spacing scale (`XS=4`, `SM=8`, `MD=12`, `LG=16`, `XL=20`, `XXL=24`, in px).
  Use these constants for margins, padding, and gaps so the layout remains consistent and easy to retheme.

### Qt resources

Icons and QSS stylesheets are embedded in the compiled `resources_qrc.py` module and accessed through the Qt virtual
filesystem. All virtual paths are declared as typed `StrEnum` members in `resources/paths.py` (e.g.
`Icons.BATTERY`, `Styles.TOPBAR`). Any new asset must be:

1. Added to `resources/icons/` or `resources/styles/`
2. Registered in `resources/syncdose.qrc`
3. Assigned a `StrEnum` entry in the correct class in `resources/paths.py`
4. Recompiled: `pyside6-rcc resources/syncdose.qrc -o resources_qrc.py`

---

## Screen Navigation

`MainWindow` contains a `QStackedWidget` with two screens registered in this order:

```
index 0 — LoginScreen      (default, shown on launch)
index 1 — DashboardScreen  (shown after a device connects)
```

Navigation is handled entirely by `NavigationManager`, a thin `QObject` singleton that exposes a `navigate` signal:

```python
# Anywhere in the app — switch to the dashboard:
navigation_manager.go_to_screen(Screen.DASHBOARD)

# Switch back to login (e.g. after device disconnects):
navigation_manager.go_to_screen(Screen.LOGIN)
```

`MainWindow._connect_signals()` wires `navigation_manager.navigate` to its own `_change_page` slot, so the window
itself never decides *when* to change screens — it only executes the change when told to. This keeps `MainWindow`
free of business logic and makes navigation trivially testable.

| Signal / call                                       | Who triggers it                            | Effect                         |
|-----------------------------------------------------|--------------------------------------------|--------------------------------|
| `navigation_manager.go_to_screen(Screen.DASHBOARD)` | `DeviceViewModel` on `device_connected`    | Switches to `DashboardScreen`  |
| `navigation_manager.go_to_screen(Screen.LOGIN)`     | `DeviceViewModel` on `device_disconnected` | Switches back to `LoginScreen` |

---

## Login Screen

The login screen is split into two panels in a **5 : 6** stretch ratio:

### Left Panel — QR Pairing

- Displays the app logo, a live QR code encoding the host's local IP address, and scan instructions
- The QR widget (`QR`) renders with rounded corners and teal corner-bracket decorations
- A **Refresh QR** button regenerates the code on demand by calling `network.get_ip()` again
- A pulsing-dot **"Waiting for connection…"** indicator sits below the button, animated in CSS via a
  `QPropertyAnimation`

### Right Panel — Previously Connected Devices

- Lists previously paired devices as `PreviousDeviceCard` widgets
- Each card shows device name, OS label, tag, status badge (online / recent / idle), and last-seen time
- On hover, the status column is replaced by a **Connect →** button that calls
  `connectivity_service.connect_to_device(ip)`
- An "End-to-end encrypted" footer anchors the bottom of the panel

---

## Services

### `ConnectivityService`

Manages the TauSync TCP connection lifecycle. Spawns a `threading.Thread` (not a `QThread`) to block on
`TauSync.listen()` without freezing the UI. A `QThread` is intentionally avoided because TauSync uses blocking .NET
async calls via pythonnet — running those from a Qt-managed native thread corrupts the CLR stack and causes a fatal
`0xC0000409` crash.

PySide6 handles cross-thread signal emission automatically via queued connections.

| Signal                | Payload        | Emitted when                                           |
|-----------------------|----------------|--------------------------------------------------------|
| `device_connected`    | —              | `listen()` returns, or `connect_to_device()` completes |
| `device_disconnected` | —              | `disconnect_device()` disposes the connection          |
| `connection_error`    | `str`          | `listen()` raises an exception                         |
| `device_info_ready`   | `DeviceEntity` | All channel reads in `get_device_info()` finish        |

The `@threaded` decorator (defined at module level in `connectivity.py`) wraps any bound method to run on a new
daemon `threading.Thread`, appending it to `self._threads` so it can be joined on disconnect.

---

## Serializers

Serializers map between **typed Python entities** and **SQLite row tuples** used in parameterized queries. They live
in `serializers/` and implement the generic `ISerializer[T, K]` interface from `serializers/interfaces/base.py`:

| Method                                 | Description                                                                      |
|----------------------------------------|----------------------------------------------------------------------------------|
| `serialize(entity: T) → tuple \| None` | Convert an entity into a positional tuple for a parameterized `INSERT`/`REPLACE` |
| `deserialize(row: tuple) → T \| None`  | Reconstruct a typed entity from a `sqlite3` row; returns `None` for empty rows   |

### `DeviceSerializer`

Maps `DeviceEntity ↔ 10-column row tuple` in the order `(id, name, os, tag, last_connected, battery_level,
battery_charging, storage_used, storage_total, ip)`. Coerces `last_connected` between `datetime.date` and an
ISO-format string (`%Y-%m-%d`) on the boundary. Returns `None` for a `None` entity or an empty row.

### `ToolSerializer`

Maps `ToolEntity ↔ 4-column row tuple` in the order `(title, description, icon_path, is_enabled)`.

---

## Database

Both repositories share a single SQLite file at `data/app.db`, created automatically on the first launch.
No migration tooling is needed — each repository calls `CREATE TABLE IF NOT EXISTS` on construction.

### Schema

**`devices` table** — managed by `DeviceRepository`:

| Column             | Type               | Notes                                           |
|--------------------|--------------------|-------------------------------------------------|
| `id`               | `TEXT PRIMARY KEY` | UUID; generated if the device does not send one |
| `name`             | `TEXT`             | Human-readable device name                      |
| `os`               | `TEXT`             | OS label (e.g. `"Android 14"`)                  |
| `tag`              | `TEXT`             | User-assigned tag; defaults to `"default"`      |
| `last_connected`   | `DATETIME`         | ISO date string (`%Y-%m-%d`)                    |
| `battery_level`    | `INTEGER`          | 0–100                                           |
| `battery_charging` | `BOOLEAN`          | `1` = charging                                  |
| `storage_used`     | `INTEGER`          | Bytes used                                      |
| `storage_total`    | `INTEGER`          | Total bytes                                     |
| `ip`               | `TEXT`             | Last known IP address                           |

**`tools` table** — managed by `ToolRepository`:

| Column        | Type               | Notes                                                     |
|---------------|--------------------|-----------------------------------------------------------|
| `title`       | `TEXT PRIMARY KEY` | Tool name; also used as the display label                 |
| `description` | `TEXT`             | Short description shown on the tool card                  |
| `icon_path`   | `TEXT`             | Qt virtual filesystem path (e.g. `":/icons/android.svg"`) |
| `is_enabled`  | `BOOLEAN`          | `1` = shown in the tools grid                             |

### Seed data

`ToolRepository` seeds 10 default tools (`Tool 1` … `Tool 10`) into the `tools` table when the table is empty
(i.e. on a fresh install). Seeds are only written once — runtime mutations survive restarts.
To reset to defaults, delete `data/app.db` and relaunch.

### Data flow summary

```
data/app.db
  └─ Repository.get_all() ──► Serializer.deserialize(row) ──► Entities ──► ViewModel ──► View

View ──► ViewModel ──► Repository.save(entity) ──► Serializer.serialize(entity) ──► data/app.db
```

---

## Repository Interfaces

All repositories are built on a typed abstract base in `repositories/interfaces/base.py`, making them easy to
swap or mock in tests.

### `IRepository[T, K]`

| Method                         | Description                          |
|--------------------------------|--------------------------------------|
| `get_by_id(id: K) → T \| None` | Fetch a single entity by its ID      |
| `get_all() → list[T]`          | Fetch all entities                   |
| `save(entity: T) → None`       | Persist an entity (insert or update) |
| `delete(id: K) → None`         | Remove an entity by ID               |

### Why interfaces?

ViewModels depend only on the interface type, not the concrete class. This means:

- Unit tests inject a stub repository without touching `RepositoryManager`
- The data source (JSON file, IPC, network) can be swapped behind the interface without changing any ViewModel or View

---

## Configuration

### Tools

Tools are stored in the `tools` table of `data/app.db`. To modify them, either:

- **Edit via SQL** — open `data/app.db` with any SQLite client (e.g. DB Browser for SQLite) and
  `UPDATE tools SET is_enabled = 0 WHERE title = 'Tool 3';`
- **Reset to defaults** — delete `data/app.db` and relaunch; `ToolRepository` will re-seed the 10 default tools
- **Add a new tool** — insert a row directly or implement a UI action that calls `ToolRepository.save(entity)`

The seed defaults are defined in `_SEED_TOOLS` at the top of `repositories/tool.py`.

### Device History

Previously connected devices are stored in the `devices` table of `data/app.db`. The database is updated
automatically each time a device connects. To clear all device history, delete `data/app.db` and relaunch.

---

## License

See `LICENSE` for details.

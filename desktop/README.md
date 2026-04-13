# SyncDose — Windows Client

A desktop dashboard application for monitoring and managing connected Android devices on Windows. Built with Python and
PySide6, SyncDose provides a clean, real-time view of device status including battery, storage, connection state, and a
configurable tools grid.

---

## Features

- 📱 **Device Dashboard** — View connected device name, type, battery level, charging status, and storage usage at a
  glance
- 🔌 **Connection Status** — Live connection indicator with a pulsing dot and connection pill widget
- 🛠️ **Tools Grid** — Configurable grid of action tools loaded from `data/tool.json`, with enabled/disabled states
- 🔑 **Login Screen** — QR code pairing panel + scrollable list of previously connected devices with hover-to-connect
  cards
- 🧭 **Sidebar Navigation** — Icon-based sidebar with logo and navigation items
- 🎨 **Custom Theming** — QSS stylesheets per component under `resources/styles/`, with a centralized color palette
- 🔔 **System Tray** — Minimize-to-tray on close; restore via double-click or right-click context menu

---

## Project Structure

```
desktop/
├── run.py                   # Dev launcher — compiles resources, runs tests, then starts the app
├── main.py                  # Entry point — bootstraps QApplication and MainWindow
├── requirements.txt
├── data/
│   ├── device_info.json     # Static device info seed data
│   ├── previous_devices.json# Persisted list of previously connected devices
│   └── tool.json            # Tool definitions (title, icon, enabled state)
├── dto/                     # Data Transfer Objects (device info, previous devices, tools)
├── entities/                # Domain entities with typed dataclasses
│   ├── device_info.py       # DeviceBaseInfoEntity and typed subclasses (battery, storage, general)
│   ├── current_device_info.py # CurrentDeviceInfo (ip, name) — active session data
│   └── previous_device.py  # PreviousDeviceEntity — login screen device list entries
├── enums/
│   ├── device_type.py       # DeviceType enum (DEVICE_NAME, DEVICE_TYPE, BATTERY, STORAGE)
│   └── device_status.py     # DeviceStatus StrEnum (ONLINE, RECENT, IDLE) — login screen badge states
├── layouts/
│   └── flow_layout.py       # Custom Qt flow layout for the tools grid
├── repositories/            # Data access layer
│   ├── device_info.py       # DeviceInfoRepository
│   ├── previous_device.py   # PreviousDeviceRepository
│   ├── tool.py              # ToolRepository
│   └── interfaces/          # Abstract base interfaces (IRepository, IDeviceInfoRepository,
│                            # IPreviousDeviceRepository, IToolRepository)
├── resources/
│   ├── colors.py            # Two-layer color system: Palette (raw hex) → Colors (semantic) → component enums
│   ├── spacing.py           # Spacing scale constants (XS=4px through XXL=24px)
│   ├── paths.py             # Qt virtual filesystem paths as typed StrEnums:
│   │                        #   Icons, Styles, NavigationStyles, DashboardStyles,
│   │                        #   LoginStyles, IndicatorStyles
│   ├── icons/               # SVG icons (logo, battery, storage, smartphone, refresh, disconnect, etc.)
│   └── styles/              # Per-component QSS stylesheets, mirroring the views/ widget tree
│       ├── dashboard/       # info_card.qss, tool_card.qss, battery_info.qss, storage_info.qss, etc.
│       ├── indicators/      # connection_pill.qss
│       ├── login/           # left-panel.qss, right-panel.qss
│       ├── navigation/      # sidebar.qss, container.qss, item.qss
│       ├── divider.qss
│       ├── topbar.qss
│       ├── tray-menu.qss
│       └── logo_widget.qss
├── serializers/             # Convert entities ↔ raw dicts for JSON persistence
│   ├── interfaces/
│   │   └── base.py          # ISerializer[T, K] — serialize() and deserialize() contract
│   ├── device_info.py       # DeviceInfoSerializer
│   ├── previous_device.py   # PreviousDeviceSerializer
│   └── tool.py              # ToolSerializer
├── services/                # Background services (non-UI)
│   └── connectivity.py      # ConnectivityService — TauSync TCP lifecycle on a threading.Thread
├── stores/                  # Read/write JSON files using a serializer
│   ├── interfaces/
│   │   └── base.py          # IStore[T, K] — load() and save() contract
│   ├── device_info.py       # DeviceInfoStore — loads/saves data/device_info.json
│   ├── previous_device.py   # PreviousDeviceStore — loads/saves data/previous_devices.json
│   └── tool.py              # ToolStore — loads/saves data/tool.json
├── utils/
│   ├── repository_manger.py # RepositoryManager singleton — DI root for all repositories
│   ├── services_manager.py  # ServicesManager singleton — DI root for all services
│   ├── network.py           # get_ip() — resolves the host's local IP address for QR generation
│   ├── navigation_stack.py  # Navigation history stack
│   ├── styles.py            # Style loading utilities
│   └── meta.py              # ABCQObjectMeta — metaclass bridging ABC and QObject
├── viewmodels/              # PySide6 QObject ViewModels with Signals/Slots
│   ├── device_info.py       # DeviceInfoViewModel
│   ├── previous_device.py   # PreviousDeviceViewModel
│   └── tool.py              # ToolViewModel
├── views/
│   ├── screens/
│   │   ├── login.py              # LoginScreen — LeftPanel + RightPanel side by side
│   │   └── dashboard_screen.py   # DashboardScreen — sidebar + topbar + content
│   └── widgets/
│       ├── dashboard/            # Battery info, storage info, tool cards, phone details row
│       ├── indicators/           # ConnectionPill, PulsingDot
│       ├── login/                # LeftPanel, RightPanel, QR, DeviceCard, DeviceIcon
│       ├── navigation/           # Sidebar, nav items, container
│       ├── topbar.py
│       ├── bar.py
│       └── logo_widget.py
├── unit_tests/
│   ├── repositories/
│   ├── serializers/
│   ├── services/
│   ├── stores/
│   └── view_model/
└── windows/
    └── main_window.py       # QMainWindow — QStackedWidget screen manager + system tray
```

---

## Architecture

SyncDose follows an **MVVM (Model-View-ViewModel)** pattern:

- **Entities** are plain Python dataclasses representing domain objects
- **Repositories** handle data loading and emit PySide6 signals on changes
- **ViewModels** sit between repositories and views — they convert entities to DTOs and re-emit signals that views bind
  to
- **Views** are PySide6 widgets that connect to ViewModel signals and update the UI reactively
- **RepositoryManager** is a global singleton that holds all repository instances (`utils/repository_manger.py`)
- **ServicesManager** is a global singleton that holds all service instances (`utils/services_manager.py`)

### DI roots

| Singleton | Module | Holds |
|---|---|---|
| `repository_manager` | `utils/repository_manger.py` | `tools_repository`, `device_repository`, `previous_device_repository` |
| `services_manager` | `utils/services_manager.py` | `connectivity_service` |

ViewModels import from `repository_manager`; `MainWindow` wires connectivity signals from `services_manager`.

---

## Screen Navigation

`MainWindow` uses a `QStackedWidget` with two screens:

```
index 0 — LoginScreen      (shown on launch, waiting for a device to connect)
index 1 — DashboardScreen  (shown after ConnectivityService emits device_connected)
```

Navigation is driven entirely by `ConnectivityService` signals:

- `device_connected` → switch to `DashboardScreen`
- `device_disconnected` → switch back to `LoginScreen`

---

## Login Screen

The login screen is split into two panels in a **5 : 6** stretch ratio:

### Left Panel — QR Pairing
- Displays the app logo, a live QR code encoding the host's local IP address, and scan instructions
- The QR widget (`QR`) renders with rounded corners and teal corner-bracket decorations
- A **Refresh QR** button regenerates the code on demand
- A pulsing-dot **"Waiting for connection…"** indicator sits below the button

### Right Panel — Previously Connected Devices
- Lists previously paired devices as `DeviceCard` widgets loaded from `data/previous_devices.json`
- Each card shows device name, OS label, tag, status badge (online / recent / idle), and last-seen time
- On hover, the status column is replaced by a **Connect →** button
- An "End-to-end encrypted" footer anchors the bottom of the panel

---

## Services

### `ConnectivityService`

Manages the TauSync TCP connection lifecycle. Spawns a `threading.Thread` (not a `QThread`) to block on
`TauSync.listen()` without freezing the UI. A `QThread` is intentionally avoided because TauSync uses blocking .NET
async calls via pythonnet — running those from a Qt-managed native thread corrupts the CLR stack and causes a fatal
`0xC0000409` crash.

PySide6 handles cross-thread signal emission automatically via queued connections.

| Signal | Emitted when |
|---|---|
| `device_connected` | `listen()` returns successfully, or `connect_to_device()` completes |
| `device_disconnected` | `disconnect_device()` disposes the connection |
| `connection_error(str)` | `listen()` raises an exception |

---

## Serializers

Serializers handle converting between **typed Python entities** and **raw dicts** suitable for JSON. They live in
`serializers/` and all implement the generic `ISerializer[T, K]` interface from `serializers/interfaces/base.py`:

| Method                     | Description                                               |
|----------------------------|-----------------------------------------------------------|
| `serialize(data: T) → K`   | Convert an entity (or dict of entities) into a plain dict |
| `deserialize(data: K) → T` | Reconstruct typed entity objects from a plain dict        |

### `DeviceInfoSerializer`

Serializes/deserializes `Dict[DeviceType, DeviceBaseInfoEntity]`. During deserialization, it uses a `TYPE_MAP` to
dispatch to the correct entity subclass based on the `DeviceType` key — so a battery entry becomes a
`DeviceBatteryInfoEntity`, a storage entry becomes a `DeviceStorageInfoEntity`, and name/type entries become
`DeviceGeneralInfoEntity`.

### `PreviousDeviceSerializer`

Serializes/deserializes `Dict[str, PreviousDeviceEntity]`. Each key is the device ID string; values are hydrated back
into `PreviousDeviceEntity` dataclasses including the `DeviceStatus` enum field.

### `ToolSerializer`

Serializes/deserializes `Dict[str, ToolEntity]`. Straightforward — each key is the tool name string and each value is
hydrated back into a `ToolEntity` dataclass via `**kwargs`.

---

## Stores

Stores handle the **file I/O layer** — reading from and writing to files on disk. They live in `stores/` and implement
`IStore[T, K]` from `stores/interfaces/base.py`:

| Method                 | Description                                          |
|------------------------|------------------------------------------------------|
| `load() → T`           | Read JSON from disk and return deserialized entities |
| `save(data: K) → None` | Serialize entities and write JSON to disk            |

Each store accepts an optional `serializer` and `json_path` at construction time, keeping I/O and data transformation
separate. In tests, you can pass a mock serializer or a fixture file path instead of the defaults.

### `DeviceInfoStore`

Reads/writes `data/device_info.json`. Returns `{}` instead of raising if the file doesn't exist yet.

### `PreviousDeviceStore`

Reads/writes `data/previous_devices.json`. Same safe fallback behavior on a missing file.

### `ToolStore`

Reads/writes `data/tool.json`. Same safe fallback behavior on a missing file.

### Data flow summary

```
file
  └─ Store.load() ──► Serializer.deserialize() ──► Entities ──► Repository ──► ViewModel ──► View

View ──► ViewModel ──► Repository ──► Store.save() ──► Serializer.serialize() ──► file
```

---

## Repository Interfaces

All repositories are built on a typed abstract base, making them easy to swap or mock in tests.

### `IRepository[T, K]`

The generic base interface (`repositories/interfaces/base.py`) that every repository must implement:

| Method                         | Description                          |
|--------------------------------|--------------------------------------|
| `get_by_id(id: K) → T \| None` | Fetch a single entity by its ID      |
| `get_all() → list[T]`          | Fetch all entities                   |
| `save(entity: T) → None`       | Persist an entity (insert or update) |
| `delete(id: K) → None`         | Remove an entity by ID               |

### `IDeviceInfoRepository`

Extends `IRepository[DeviceBaseInfoEntity, DeviceType]`. Uses `DeviceType` as the key, so each device info slot (name,
type, battery, storage) is addressed by its enum value. Also declares two PySide6 signals:

- `device_info_saved` — emitted after a successful `save()`
- `device_info_deleted` — emitted after a successful `delete()`

### `IPreviousDeviceRepository`

Extends `IRepository[PreviousDeviceEntity, str]`. Uses device ID string as the key. Declares:

- `device_saved` — emitted after a successful `save()`
- `device_deleted` — emitted after a successful `delete()`

### `IToolRepository`

Extends `IRepository[ToolEntity, str]`. Adds one extra method on top of the base:

| Method                                 | Description                                  |
|----------------------------------------|----------------------------------------------|
| `get_all_enabled() → list[ToolEntity]` | Returns only tools where `is_enabled = True` |

Also declares:

- `tool_saved` — emitted after a successful `save()`
- `tool_deleted` — emitted after a successful `delete()`

### Why interfaces?

ViewModels depend only on the interface types, not the concrete repository classes. This means:

- Unit tests can inject a mock or stub repository without touching `RepositoryManager`
- The data source (JSON file, IPC, network) can be swapped behind the interface without changing any ViewModel or View
  code

---

## Requirements

- Python 3.10+
- PySide6
- pythonnet >= 3.0.0
- qrcode[pil]

Install dependencies:

```bash
pip install -r requirements.txt
```

> PySide6 is required but not listed in `requirements.txt` — install it separately:
> ```bash
> pip install PySide6
> ```

---

## Running the App

### Standard launch (compiles resources, then starts)

```bash
python run.py
```

### With tests before launch

```bash
python run.py --test
```

### Direct launch (skip resource compilation)

```bash
python main.py
```

The dashboard window will open at 1100×720. Closing the window minimizes it to the system tray — right-click the tray
icon to quit.

---

## Running Tests

```bash
pytest unit_tests/
```

Tests cover repositories, serializers, stores, services, and view-models using `pytest` fixtures defined in
`unit_tests/conftest.py`.

---

## Configuration

### Tools

Edit `data/tool.json` to configure the tools shown in the dashboard grid:

```json
{
  "My Tool": {
    "title": "My Tool",
    "description": "Does something useful",
    "icon_path": ":/icons/android.svg",
    "icon_background_color": "#FFFFFF",
    "is_enabled": true
  }
}
```

### Device Info

Edit `data/device_info.json` to set the seed device data displayed in the dashboard (device name, type, battery,
storage).

### Previously Connected Devices

Edit `data/previous_devices.json` to pre-populate the login screen device list. Each entry requires:

```json
{
  "device-id-001": {
    "id": "device-id-001",
    "name": "Pixel 8 Pro",
    "os_label": "Android 14",
    "tag": "Home",
    "icon_color": "#4CAF50",
    "status": "online",
    "last_seen": "now"
  }
}
```

Valid `status` values: `"online"`, `"recent"`, `"idle"`.

---

## License

See `LICENSE` for details.

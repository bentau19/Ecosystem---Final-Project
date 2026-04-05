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
- 🧭 **Sidebar Navigation** — Icon-based sidebar with logo and navigation items
- 🎨 **Custom Theming** — QSS stylesheets per component under `resources/styles/`, with a centralized color palette

---

## Project Structure

```
windows/
├── main.py                  # Entry point — bootstraps QApplication and MainWindow
├── requirements.txt
├── data/
│   ├── device_info.json     # Static device info seed data
│   └── tool.json            # Tool definitions (title, icon, enabled state)
├── dto/                     # Data Transfer Objects (device info, tools)
├── entities/                # Domain entities with typed dataclasses
├── enums/
│   └── device_type.py       # DeviceType enum (DEVICE_NAME, DEVICE_TYPE, BATTERY, STORAGE)
├── layouts/
│   └── flow_layout.py       # Custom Qt flow layout for the tools grid
├── repositories/            # Data access layer (DeviceInfoRepository, ToolRepository)
│   └── interfaces/          # Abstract base interfaces (IRepository, IDeviceInfoRepository, IToolRepository)
├── resources/
│   ├── colors.py            # Two-layer color system: Palette (raw hex) → Colors (semantic) → component-specific enums
│   ├── spacing.py           # Spacing scale constants (XS=4px through XXL=24px)
│   ├── paths.py             # Qt virtual filesystem paths for icons and QSS files, as typed StrEnums
│   ├── icons/               # SVG icons registered in Qt's virtual filesystem (logo, battery, storage, smartphone, etc.)
│   └── styles/              # Per-component QSS stylesheets, mirroring the views/ widget tree
│       ├── dashboard/       # info_card.qss, tool_card.qss, battery_info.qss, storage_info.qss, etc.
│       ├── indicators/      # connection_pill.qss
│       ├── navigation/      # sidebar.qss, container.qss, item.qss
│       ├── divider.qss
│       ├── topbar.qss
│       └── logo_widget.qss
├── serializers/             # Convert entities ↔ raw dicts for JSON persistence
│   ├── interfaces/
│   │   └── base.py          # ISerializer[T, K] — serialize() and deserialize() contract
│   ├── device_info.py       # DeviceInfoSerializer — maps DeviceType keys to typed entity subclasses
│   └── tool.py              # ToolSerializer — maps string keys to ToolEntity dataclasses
├── stores/                  # Read/write JSON files using a serializer
│   ├── interfaces/
│   │   └── base.py          # IStore[T, K] — load() and save() contract
│   ├── device_info.py       # DeviceInfoStore — loads/saves data/device_info.json
│   └── tool.py              # ToolStore — loads/saves data/tool.json
├── utils/
│   ├── app_state.py         # Global singleton AppState (holds repository instances)
│   ├── navigation_stack.py  # Navigation history stack
│   ├── styles.py            # Style loading utilities
│   └── meta.py              # App metadata
├── viewmodels/              # PySide6 QObject ViewModels with Signals/Slots
│   ├── device_info.py
│   └── tool.py
├── views/
│   ├── screens/
│   │   └── dashboard_screen.py   # Main dashboard screen (sidebar + topbar + content)
│   └── widgets/
│       ├── dashboard/            # Battery info, storage info, tool cards, phone details row
│       ├── indicators/           # Connection pill, pulsing dot
│       ├── navigation/           # Sidebar, nav items, container
│       ├── topbar.py
│       ├── bar.py
│       └── logo_widget.py
├── unit_tests/
│   ├── repositories/
│   ├── serializers/
│   ├── stores/
│   └── view_model/
└── windows/
    └── main_window.py       # QMainWindow wrapper
```

---

## Architecture

SyncDose follows an **MVVM (Model-View-ViewModel)** pattern:

- **Entities** are plain Python dataclasses representing domain objects
- **Repositories** handle data loading and emit PySide6 signals on changes
- **ViewModels** sit between repositories and views — they convert entities to DTOs and re-emit signals that views bind
  to
- **Views** are PySide6 widgets that connect to ViewModel signals and update the UI reactively
- **AppState** is a global singleton that holds shared repository instances, accessible throughout the app

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

### `ToolSerializer`

Serializes/deserializes `Dict[str, ToolEntity]`. Straightforward — each key is the tool name string and each value is
hydrated back into a `ToolEntity` dataclass via `**kwargs`.

---

## Stores

Stores handle the **file I/O layer** — reading from and writing to files on disk or elsewhere. They live in `stores/`
and implement `IStore[T, K]` from `stores/interfaces/base.py`:

| Method                 | Description                                          |
|------------------------|------------------------------------------------------|
| `load() → T`           | Read JSON from disk and return deserialized entities |
| `save(data: K) → None` | Serialize entities and write JSON to disk            |

Each store is injected with a serializer at construction time, keeping I/O and data transformation separate:

Each store accepts an optional ```serializer``` and ```json_path``` at construction time, keeping I/O and data transformation
separate. In tests, you can pass a mock serializer or a fixture file path instead of the defaults.

### `DeviceInfoStore`

Reads/writes `data/device_info.json`. Returns `{}` instead of raising if the file doesn't exist yet.

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

- Unit tests can inject a mock or stub repository without touching `AppState`
- The data source (JSON file, IPC, network) can be swapped behind the interface without changing any ViewModel or View
  code

---

## Requirements

- Python 3.10+
- PySide6
- pythonnet >= 3.0.0

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

From the `windows/` directory:

```bash
python main.py
```

The dashboard window will open at 1100×720.

---

## Running Tests

From the `windows/` directory:

```bash
pytest unit_tests/
```

Tests cover repositories, serializers, stores, and view-models (`unit_tests/repositories/`, `unit_tests/serializers/`,
`unit_tests/stores/`, `unit_tests/view_model/`) using `pytest` fixtures defined in `unit_tests/conftest.py`.

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

---

## License

See `LICENSE` for details.
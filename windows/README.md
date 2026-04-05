# SyncDose — Windows Client

A desktop dashboard application for monitoring and managing connected Android devices on Windows. Built with Python and PySide6, SyncDose provides a clean, real-time view of device status including battery, storage, connection state, and a configurable tools grid.

---

## Features

- 📱 **Device Dashboard** — View connected device name, type, battery level, charging status, and storage usage at a glance
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
│   └── interfaces/          # Abstract base interfaces for repositories
├── resources/
│   ├── colors.py            # Centralized color constants
│   ├── spacing.py           # Spacing constants
│   ├── paths.py             # Resource path helpers
│   ├── icons/               # SVG icons (battery, storage, smartphone, logo, etc.)
│   └── styles/              # Per-component QSS stylesheets
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
- **ViewModels** sit between repositories and views — they convert entities to DTOs and re-emit signals that views bind to
- **Views** are PySide6 widgets that connect to ViewModel signals and update the UI reactively
- **AppState** is a global singleton that holds shared repository instances, accessible throughout the app

---

## Requirements

- Python 3.10+
- PySide6
- pythonnet >= 3.0.0

Install dependencies:

```bash
pip install -r requirements.txt
```
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

Tests cover repositories, serializers, stores, and viewmodels using `pytest` fixtures defined in `unit_tests/conftest.py`.

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

Edit `data/device_info.json` to set the seed device data displayed in the dashboard (device name, type, battery, storage).

---

## License

See `LICENSE` for details.
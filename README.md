# Ecosystem

A cross-platform solution connecting Android phones to Windows PCs. The phone acts as a remote extension of the desktop — send files, view device info, and trigger actions from either side over a local Wi-Fi connection.

## Sub-projects

| Directory | Language | Description |
|---|---|---|
| [`android/`](android/) | Java (MVVM + Clean Architecture) | Android client app |
| [`desktop/`](desktop/) | Python 3.13 + PySide6 | Windows desktop client — **SyncDose** |
| [`TauSync/`](TauSync/) | C# .NET 8 + Java + Python wrapper | Proprietary TCP multiplexing protocol |

---

## Repository Structure

```
Ecosystem/
├── android/                    # Android app (Java, Min SDK 24)
│   └── app/src/main/java/com/example/android/
│       ├── domain/             # Pure Java — entities, use cases (no Android deps)
│       ├── data/               # DataSources, Repositories
│       ├── network/            # ConnectionService (Foreground Service)
│       ├── ui/                 # Fragments, Adapters, MainActivity
│       └── viewmodel/          # MainViewModel + Factory
│
├── desktop/                    # SyncDose Windows app (Python + PySide6)
│   ├── app/                    # DI root (AppState), NavigationManager, ThemeManager
│   ├── domain/                 # DTOs, Entities, Enums
│   ├── repositories/           # SQLite persistence (sqlite3)
│   ├── serializers/            # Entity ↔ row-tuple conversion
│   ├── services/               # Background threads: connectivity, file transfer, etc.
│   ├── viewmodels/             # Qt Signals + DTOs consumed by Views
│   ├── views/                  # PySide6 widgets and screens
│   ├── native/windows/pipe/    # C++ pybind11 named-pipe module (IPC with FileHandler)
│   ├── core/pipe_client.py     # FileHandler.exe entry point
│   ├── resources/              # Colors, spacing tokens, QSS, icons
│   ├── tests/                  # pytest suite
│   ├── main.py                 # App entry point (fast launch)
│   └── run.py                  # Dev launcher: compile resources → run tests → launch
│
└── TauSync/                    # Protocol library
    ├── Shared_Definitions/     # TauSync_Protocol_Spec.md (v3.1)
    ├── Tausync_Windows/        # C# .NET 8 library (TauSync.Lib.dll)
    │   └── TauSync.Lib/
    ├── Tausync_Android/        # Java Android library
    │   └── tausync-lib/
    └── windows/                # Python wrapper (tausync_py) around the .NET DLL
```

---

## Desktop — SyncDose

### Prerequisites

- Python 3.13
- Docker Desktop (for building the TauSync DLL)
- MSVC build tools (for the native named-pipe module — via Visual Studio or `ilammy/msvc-dev-cmd`)

### First-time setup

```powershell
# 1. Build the TauSync .NET DLL
cd TauSync/
docker compose up
cd ..

# 2. Build the native Windows named-pipe module
cmake -S desktop/native/windows/pipe -B desktop/native/windows/pipe/build
cmake --build desktop/native/windows/pipe/build --config Release
Copy-Item desktop/native/windows/pipe/build/Release/pipe_module.cp313-win_amd64.pyd `
          desktop/native/windows/pipe/

# 3. Create the venv and install dependencies
cd desktop/
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r ../TauSync/windows/requirements.txt
pip install -r requirements.txt
pip install ../TauSync/windows

# 4. Compile Qt resources
pyside6-rcc resources/syncdose.qrc -o resources_qrc.py
```

### Run

```powershell
# Dev launcher — compiles resources, runs all tests, then launches the app
python run.py

# Fast launch — skips compilation and tests (resources must already be compiled)
python main.py
```

### Tests

```powershell
# Full test suite
pytest desktop/

# Single module
pytest desktop/tests/repositories/test_tool.py -v
```

### Production build

Two PyInstaller executables are produced and packaged together as a single MSI:

```powershell
pyinstaller desktop/installer/specs/main_app.spec      # SyncDose.exe
pyinstaller desktop/installer/specs/file_handler.spec  # FileHandler.exe
dotnet build desktop/installer/ -c Release             # → .msi
```

`SyncDose.exe` runs as a named-pipe server on `\\.\pipe\FileSend`. `FileHandler.exe` is
registered as the Windows shell "Send with SyncDose" context-menu handler — it writes the
target file path to the pipe and exits.

---

## Android App

**Min SDK:** 29 (Android 10.0) · **Target SDK:** 36 · **JDK:** 21 · **Gradle:** 8.13

Open `android/` in Android Studio. The app uses manual DI via `MainViewModelFactory` — no
Hilt or Dagger. `ConnectionService` is a Foreground Service that keeps the TauSync socket
alive while the app is in the background.

Connection is established by scanning a QR code displayed on the SyncDose desktop app.

---

## TauSync Protocol

TauSync multiplexes named duplex channels over a single TCP connection (port 8888) using
8-byte binary frames (**TPack**: `4B LE length | 3B LE TargetID | 1B flags`).

Both sides call `connect(word)` with the same meeting word; the protocol pairs them and
returns a private duplex stream on each side. Race resolution uses the TCP server/client
role as a deterministic tiebreaker.

- **Protocol spec:** [`TauSync/Shared_Definitions/TauSync_Protocol_Spec.md`](TauSync/Shared_Definitions/TauSync_Protocol_Spec.md)
- **Python wrapper:** [`TauSync/windows/README.md`](TauSync/windows/README.md)
- **Android SDK:** [`TauSync/Tausync_Android/tausync-lib/README.md`](TauSync/Tausync_Android/tausync-lib/README.md)

---

## CI/CD

GitHub Actions (`.github/workflows/desktop.yml`) runs on every push:

1. **test** — builds TauSync DLL → builds native pipe module (MSVC) → `pip install` → `pytest desktop/`
2. **build** — builds both PyInstaller executables → `dotnet build` MSI → uploads `.msi` artifact

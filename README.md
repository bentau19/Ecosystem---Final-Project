# Ecosystem

A cross-platform solution connecting Android phones to Windows PCs. The phone acts as a remote extension of the desktop — send files, view device info, and trigger actions from either side over a local Wi-Fi connection.

## Sub-projects

| Directory | Language | Description |
|---|---|---|
| [`android/`](android/README.md) | Java · MVVM + Clean Architecture | Android companion app — device info, file transfer (both directions), backup |
| [`desktop/`](desktop/README.md) | Python 3.13 · PySide6 | **SyncDose** Windows desktop client — dashboard, tools grid, file transfer, backup, system tray |
| [`TauSync/`](TauSync/README.md) | C# .NET 8 · Java · Python wrapper | Proprietary TCP multiplexing protocol — C# library, Android Java port, Python wrapper |
| [`FileDetection/`](FileDetection/README.md) | Python · PyTorch | ML-powered backup screening — duplicate detection, corruption checks, image classification |

---

## Repository Structure

```
Ecosystem/
├── android/                    # Android app (Java, Min SDK 29)
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
│   ├── core/file_handler.py    # FileHandler.exe entry point
│   ├── resources/              # Colors, spacing tokens, QSS, icons
│   ├── tests/                  # pytest suite
│   ├── main.py                 # App entry point (fast launch)
│   └── run.py                  # Dev launcher: compile resources → run tests → launch
│
├── TauSync/                    # Protocol library
│   ├── Shared_Definitions/     # TauSync_Protocol_Spec.md (v3.1)
│   ├── Tausync_Windows/        # C# .NET 8 library (TauSync.Lib.dll)
│   │   └── TauSync.Lib/
│   ├── Tausync_Android/        # Java Android library
│   │   └── tausync-lib/
│   └── windows/                # Python wrapper (tausync_py) around the .NET DLL
│
└── FileDetection/              # ML backup screening pipeline (PyTorch)
    ├── detector.py             # Corruption detection (empty file, format-level checks)
    ├── classifer.py            # Classifier — two-stage pipeline (dups + ML)
    ├── image_classifer.py      # MobileNetV3-Large image classifier
    ├── file_duplicates.py      # xxh3_128 content-hash duplicate detection
    ├── quality.py              # Image quality scoring
    ├── similar_photos.py       # Perceptual hash visual-similarity grouping
    ├── checkers/               # Format-specific checkers (image, PDF, ZIP)
    └── dataset/                # Training data
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
pip install -r ../FileDetection/requirements.txt
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

Three executables are produced and packaged into a single bootstrapper installer
(`SyncDoseSetup.exe`):

```powershell
# Build PyInstaller executables (run from repo root)
pyinstaller desktop/installer/Package/specs/main_app.spec      # → SyncDose.exe
pyinstaller desktop/installer/Package/specs/file_handler.spec  # → FileHandler.exe
# VirtualDrive.exe is pre-built — no build step needed

# Package as MSI + Bundle bootstrapper
dotnet build desktop/installer/ -c Release             # → SyncDoseSetup.exe
```

`SyncDose.exe` is the main dashboard, acting as a named-pipe server on both
`\\.\pipe\FileSend` and `\\.\pipe\SyncDoseVDrive`. `FileHandler.exe` is registered as the
Windows shell "Send with SyncDose" context-menu handler — it writes the target file path
to `\\.\pipe\FileSend` and exits. `VirtualDrive.exe` is a native C++ WinFsp filesystem that
mounts the connected phone as a Windows drive letter, forwarding every Explorer op to
`SyncDose.exe` via `\\.\pipe\SyncDoseVDrive`.

`SyncDoseSetup.exe` (the WiX Bundle) auto-installs **.NET 8 Runtime** and **WinFSP 2.0** if
they are missing before running the MSI — end users only need this one file.

---

## Android App

**Min SDK:** 29 (Android 10.0) · **Target SDK:** 36 · **JDK:** 21 · **Gradle:** 9.5.1

Open `android/` in Android Studio. The app uses manual DI via `MainViewModelFactory` — no
Hilt or Dagger. `ConnectivityService` is a Foreground Service that keeps the TauSync socket
alive while the app is in the background.

Connection is established either by scanning a QR code (Wi-Fi) or via Bluetooth pairing (BLE discovery + hybrid BT/Wi-Fi). The desktop app lets the user switch between modes from the login screen; a first-time Bluetooth pairing is remembered for instant reconnect on subsequent sessions.

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
2. **build** — builds both PyInstaller executables (SyncDose + FileHandler) → `dotnet build` Bundle → uploads `SyncDoseSetup.exe` artifact

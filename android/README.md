# 📱 Android Ecosystem App - Project Architecture

This project follows the **Clean Architecture** principles and the **MVVM (Model-View-ViewModel)** design pattern. The architecture is designed to be modular, scalable, and easy to maintain, ensuring a strict separation between UI, business logic, and network communication.

---

## 📂 Project Structure

```plaintext
app/src/main/java/com/example/android/
│
├── 📂 ui/                         # Presentation Layer
│   ├── 📂 activities/             # Main Host Activity (MainActivity)
│   ├── 📂 fragments/              # Screens (Connect, Actions Dashboard)
│   ├── 📂 adapters/               # RecyclerView adapters (ToolsAdapter)
│   └── 📂 models/                 # UI-specific models (ToolItem)
│
├── 📂 viewmodel/                  # Logic Layer (UI State Management)
│   ├── MainViewModel.java         # Global state (Connection, PC Name, Battery)
│   ├── BackupViewModel.java       # Specific logic for file transfer features
│   └── AntivirusViewModel.java    # Logic for scanning and security features
│
├── 📂 network/                    # Communication Layer (Remote Data Source)
│   ├── ConnectionService.java     # Foreground Service for persistent connection
│   ├── SocketManager.java         # TCP Socket handling (Send/Receive bytes)
│   └── PacketParser.java          # Protocol parsing and data framing
│
├── 📂 data/                       # Data Layer (Single Source of Truth)
│   ├── 📂 models/                 # Core Business Entities
│   │   ├── 📂 entities/           # DeviceConnectionState, LocalDeviceInfo
│   │   └── 📂 enums/              # ConnectionType (WIFI, BLUETOOTH)
│   ├── 📂 repositories/           # Domain logic (DeviceRepository)
│   └── 📂 serializers/            # JSON mapping (DeviceSerializer)
│
└── 📂 utils/                      # Utilities & Shared Helpers
    ├── DeviceUtils.java           # Hardware access (Battery/Storage)
    └── NetworkUtils.java          # IP and Connectivity helpers
```

## 🏗️ Architectural Decisions

### 1. Single Activity Architecture
The application uses a single MainActivity as a container, switching between various Fragments. This approach provides a smoother user experience, optimized memory management, and simplified shared element transitions.

### 2. MVVM Pattern
By separating the UI (Fragments) from the logic (ViewModels), the app ensures that the business logic survives configuration changes (like screen rotations). The UI "observes" data changes via LiveData, making the interface reactive and stable.

### 3. Foreground Service Strategy
To maintain a stable ecosystem connection between the Phone and the PC, we utilize a Foreground Service. This ensures the Socket connection remains active even when the user is not actively interacting with the app.

### 4. Repository Pattern
Each feature (Backup, Antivirus, etc.) has its own Repository. This layer abstracts the data source, allowing the ViewModel to request data without knowing whether it's coming from a local scan or a network response from the PC.

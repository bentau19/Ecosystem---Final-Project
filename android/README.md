# 📱 Android Ecosystem App - Project Architecture

This project follows **Clean Architecture** principles combined with the **MVVM (Model-View-ViewModel)** design pattern. The architecture is strictly layered to ensure a clear separation of concerns, high testability, and scalability.

---

## 📂 Project Structure

```plaintext
app/src/main/java/com/example/android/
│
├── 📂 ui/                        # Presentation Layer (Views)
│   ├── 📂 activities/            # Main Host Activity
│   ├── 📂 fragments/             # Connect Screen, Actions Dashboard
│   ├── 📂 adapters/              # RecyclerView adapters (ToolsAdapter)
│   └── 📂 models/                # UI-specific models (ToolItem)
│
├── 📂 viewmodel/                 # Logic Layer (UI State & ViewModelFactory)
│   ├── MainViewModel.java        # Coordinates between Use Cases and UI
│   └── MainViewModelFactory.java # Dependency Injection (Manual DI)
│
├── 📂 domain/                    # Business Logic Layer (Pure Java)
│   ├── 📂 entities/              # DeviceConnectionState, LocalDeviceInfo, RemoteDeviceInfo
│   ├── 📂 enums/                 # ConnectionType (WIFI, BLUETOOTH)
│   └── 📂 usecases/              # Single Action Logic (ParseQr, RefreshStats, ConnectToDevice)
│
├── 📂 data/                      # Data Access Layer
│   ├── 📂 datasource/            # Raw System Access (SystemDataSource - Context dependent)
│   └── 📂 repositories/          # Single Source of Truth (DeviceRepository)
│
├── 📂 serializers/               # Data Transformation Layer
│   └── DeviceSerializer.java     # JSON Mapping & Serialization logic
│
├── 📂 network/                   # Communication Layer
│   ├── ConnectionService.java    # Foreground Service for persistent socket connection
│   ├── SocketManager.java        # TCP Socket handling
│   └── PacketParser.java         # Protocol parsing and data framing
│
└── 📂 utils/                     # Shared Helpers
    ├── DeviceUtils.java          # Hardware helpers (Storage, Battery)
    └── NetworkUtils.java         # IP & Connectivity helpers
```

---

## 🏗️ Architectural Decisions

### 1. Clean Architecture & Layer Separation
The project is divided into Presentation, Domain, and Data layers. By moving the core logic into Use Cases, the ViewModel remains lightweight and focuses only on UI state management. The Domain layer has zero dependencies on the Android Framework, allowing for fast and reliable Unit Testing.

### 2. Single Activity Architecture
The application uses a single MainActivity as a container, switching between various Fragments. This approach provides a smoother user experience, optimized memory management, and simplified shared element transitions.

### 3. MVVM Pattern
By separating the UI (Fragments) from the logic (ViewModels), the app ensures that the business logic survives configuration changes (like screen rotations). The UI "observes" data changes via LiveData, making the interface reactive and stable.

### 4. Foreground Service Strategy
To maintain a stable ecosystem connection between the Phone and the PC, we utilize a Foreground Service. This ensures the Socket connection remains active even when the user is not actively interacting with the app.

### 5. Repository & Data Source Pattern
We distinguish between the DataSource (raw system calls) and the Repository (business logic/data management). The DeviceRepository acts as the single source of truth, managing the LiveData that the UI observes..

### 6. Manual Dependency Injection (Factory Pattern)
To maintain a "Pure Logic" ViewModel, we utilize a MainViewModelFactory. This component handles the instantiation of DataSources and Repositories, injecting them into the ViewModel. This prevents memory leaks and decouples the ViewModel from the Android Context.

---

## 🧪 Testing Strategy
The architecture is designed for 100% testability of business logic:

* **Unit Tests (src/test):** Testing ViewModels, UseCases, and Repositories using Mockito to mock dependencies.

* **JUnit: Used for validating** Serialization and Data integrity.

* **Architecture Isolation:** Use Cases allow testing of specific actions (like QR parsing) without running an Android Emulator.

---

## ⚙️ Environment & Requirements

* **Android Studio:** Panda 1 | 2025.3.1 Patch 1 or newer
* **JDK:** Java 21
* **Gradle:** 8.13
* **Min SDK:** 24 (Android 7.0)
* **Target SDK:** 36

---

## 🚀 Getting Started
**1. Clone the repository:** git clone https://github.com/bentau19/Ecosystem---Final-Project.git

**2. Open in Android Studio:** Select the android folder.

**3. Gradle Sync:** Allow Android Studio to download dependencies (Mockito, ZXing).

**4. Run Tests:** Right-click the java/com.example.android (test) folder and select "Run 'All Tests'" to verify the logic.

**5. Build & Run:** Deploy to a physical device or emulator (API 24+).

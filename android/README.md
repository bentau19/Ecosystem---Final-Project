# Android App README

This folder contains the Android side of the Ecosystem / SyncDose project. The Android app connects to the desktop app through the local TauSync library, displays device and connection state, sends Android device information to the PC, and handles PC-initiated channel requests.

The app follows a Clean Architecture style with MVVM for UI state, plus a dedicated communication layer built around `TransportManager` and channel handlers.

## Modules

```text
android/
├── app/                 # Main Android application
├── gradle/              # Gradle wrapper files
├── build.gradle.kts     # Root Android build configuration
└── settings.gradle.kts  # Includes app and tausync-lib modules
```

## Source Structure

```text
app/src/main/java/com/example/android/
├── data/
│   └── datasource/
├── domain/
│   ├── entities/
│   ├── enums/
│   └── usecases/
├── enums/
├── network/
│   ├── handlers/
│   └── transport/
├── repositories/
├── serializers/
├── services/
├── testing/
├── ui/
│   ├── adapters/
│   ├── fragments/
│   ├── models/
│   └── MainActivity.java
├── utils/
└── viewmodel/
```

## Architecture Overview

The main data flow is:

```text
UI Fragment -> MainViewModel -> Use Case -> Repository -> DataSource / Service
```

For communication requests from the PC, the flow is:

```text
TauSyncTransportManager
    -> ConnectivityService.onPeerRequestsAvailable(...)
    -> ChannelHandlerRegistry
    -> specific ChannelHandler
```

## UI Layer

Location:

```text
ui/
```

Important files:

- `MainActivity.java` - Main host activity.
- `fragments/ConnectFragment.java` - Connection screen and QR flow.
- `fragments/ActionsFragment.java` - Main connected dashboard/actions screen.
- `adapters/ToolsAdapter.java` - Adapter for action/tool items.
- `models/ToolItem.java` - UI model for dashboard tools.

## ViewModel Layer

Location:

```text
viewmodel/
```

Important files:

- `MainViewModel.java` - Coordinates UI state and user actions.
- `MainViewModelFactory.java` - Manual dependency creation for the ViewModel.

The ViewModel exposes state to the UI and delegates business actions to use cases or repositories.

## Domain Layer

Location:

```text
domain/
```

Subfolders:

- `entities/` - Core app models such as `DeviceConnectionState`, `LocalDeviceInfo`, `RemoteDeviceInfo`, and `DeviceStorageStats`.
- `enums/` - App-level enums such as `ConnectionStatus` and `ConnectionType`.
- `usecases/` - Focused business actions.

Current use cases:

- `ParseQrDataUseCase.java`
- `ConnectToDeviceUseCase.java`
- `RefreshLocalStatsUseCase.java`

## Data Layer

Location:

```text
data/datasource/
```

Important file:

- `SystemDataSource.java` - Reads Android system data such as device model, device ID, local IP, battery status, charging state, and storage stats.

This is the layer that talks directly to Android framework APIs.

## Repository Layer

Location:

```text
repositories/
```

Important file:

- `DeviceRepository.java` - Single source of truth for the current device, remote PC, and connection state.

The repository owns the observable app state used by the UI and is also updated by background services when connection events arrive.

## Services

Location:

```text
services/
```

Important files:

- `ConnectivityService.java` - Foreground service that owns the active PC connection.
- `AppNotificationManager.java` - Manages the foreground service notification.

`ConnectivityService` is responsible for:

- Creating the `TauSyncTransportManager`.
- Creating and configuring the `ChannelHandlerRegistry`.
- Registering all channel handlers.
- Connecting to the PC by IP.
- Sending initial Android device info after connection.
- Dispatching PC channel requests to the correct handler.
- Cleaning up transport and repository state on disconnect.

## Network Layer

Location:

```text
network/
├── transport/
└── handlers/
```

### Transport

Location:

```text
network/transport/
```

Important files:

- `TransportManager.java` - Interface for connection, read/write, status, and peer request events.
- `TauSyncTransportManager.java` - TauSync-based implementation of `TransportManager`.
- `TransportStatus.java` - Internal transport status enum.

`TauSyncTransportManager` handles connection lifecycle, channel reads/writes, polling for peer waiting words, and status callbacks to `ConnectivityService`.

### Channel Handlers

Location:

```text
network/handlers/
```

Important files:

- `ChannelHandler.java` - Common interface for all channel handlers.
- `ChannelHandlerRegistry.java` - Maps channel names to handlers.
- `DeviceInfoChannelHandler.java` - Generic handler for Android device info channels.
- `PCNameChannelHandler.java` - Reads the PC name and updates the repository.
- `DisconnectChannelHandler.java` - Handles PC-initiated disconnects.
- `FileMetadataChannelHandler.java` - Reads file metadata sent from the PC before a file transfer.

New PC-initiated features should usually be implemented as a new `ChannelHandler` and registered in `ConnectivityService.registerChannelHandlers()`.

## Generated Channel Enums

Location:

```text
enums/
```

Important files:

- `DeviceInfoChannels.java`
- `SessionChannels.java`
- `FileTransferChannels.java`
- `FileTransferResponse.java`
- `DeviceInfoField.java`
- `Channel.java`

These files define the shared channel names used by both Android and desktop. Many of them are generated from the shared definitions under `shared/enums/`.

Avoid editing generated enum files manually. Change the shared source definitions and rerun code generation when possible.

## Device Info Flow

After a successful connection, Android sends initial device information to the desktop:

- Device name
- Android OS version
- Device ID
- Local IP address
- Battery level
- Charging state
- Total storage
- Used storage

These values are read from `SystemDataSource` and sent through `ConnectivityService.sendInitialDeviceInfo()`.

The desktop can also request values later through registered device-info channels handled by `DeviceInfoChannelHandler`.

## Serializers

Location:

```text
serializers/
```

Important file:

- `DeviceSerializer.java` - Converts device objects to and from JSON.

## Utils

Location:

```text
utils/
```

Important files:

- `DeviceUtils.java` - Device and hardware helper methods.
- `NetworkUtils.java` - Network and IP helper methods.
- `NetworkHandler.java` - Small wrapper around TauSync channel read/write operations.

`NetworkHandler` is used by `TauSyncTransportManager`; UI classes should not call it directly.

## Testing

Unit tests:

```text
app/src/test/java/com/example/android/
├── repositories/
├── serializers/
└── viewmodel/
```

Instrumentation tests:

```text
app/src/androidTest/java/com/example/android/
```

Current tests include:

- `DeviceRepositoryTest.java`
- `DeviceSerializerTest.java`
- `MainViewModelTest.java`

Manual TauSync testing activities are under:

```text
testing/
```

These are useful for local protocol checks but are not part of the normal app flow.

## Requirements

* **Android Studio:** Panda 1 | 2025.3.1 Patch 1 or newer
* **JDK:** Java 21
* **Gradle:** 8.13
* **Min SDK:** 24 (Android 7.0)
* **Target SDK:** 36

## Running The App

Open this folder in Android Studio:

```text
android/
```

Then:

**1. Clone the repository:** git clone < github project URL >

**2. Open in Android Studio:** Select the android folder.

**3. Gradle Sync:** Allow Android Studio to download dependencies (Mockito, ZXing).

**4. Run Tests:** Right-click the java/com.example.android (test) folder and select "Run 'All Tests'" to verify the logic.

**5. Build & Run:** Deploy to a physical device or emulator (API 24+).


## Adding A New PC-Initiated Channel

Recommended process:

1. Add the channel to the shared enum definitions if it must be shared with desktop.
2. Regenerate Android and desktop enums.
3. Create a new class that implements `ChannelHandler`.
4. Register it in `ConnectivityService.registerChannelHandlers()`.
5. Keep all TauSync read/write logic inside the handler or transport layer.
6. Update tests if the handler contains meaningful logic.

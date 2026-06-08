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
- `ShareReceiverActivity.java` - Invisible trampoline Activity for Android's share sheet (`ACTION_SEND`). Has no UI — it validates the intent, checks connection state, and delegates to `SendFileViewModel`, then calls `finish()` immediately. Not part of the Single Activity Architecture; acts as a system entry point (similar role to a `BroadcastReceiver`).
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

- `MainViewModel.java` - Coordinates connection state and user actions (QR scan, connect, disconnect, refresh stats).
- `MainViewModelFactory.java` - Manual dependency creation for `MainViewModel`.
- `FileTransferViewModel.java` - Coordinates incoming file transfer state (PC → Android). Exposes `getPendingRequest()` and `getTransferStatus()` LiveData, and handles user Accept / Reject decisions.
- `SendFileViewModel.java` - Coordinates outgoing file transfer state (Android → PC). Exposes `getSendStatus()` and `getCurrentFileName()` LiveData. Delegates all logic to `SendFileRepository`. Used by `ShareReceiverActivity` (not `MainActivity`) since file sending is triggered from the share sheet.

Each ViewModel is scoped to the host Activity and observed by the relevant Fragment or the Activity itself. ViewModels are split by feature to keep each one focused.

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
- `RespondToFileTransferUseCase.java` - Sends `ACCEPTED_FROM_ANDROID` or `REJECTED_FROM_ANDROID` to the PC over the response channel. Called by `ConnectivityService` on a background thread after the user decides.
- `ReceiveFileUseCase.java` - Streams file bytes from the `file_data_pc` TauSync channel directly into a MediaStore `OutputStream` in 64 KB chunks. The full file is never held in RAM, so arbitrarily large files are supported. Saves to the public Downloads folder using the MediaStore API (Android 10+, no storage permission required).

Current domain entities:

- `DeviceConnectionState.java`
- `LocalDeviceInfo.java`
- `RemoteDeviceInfo.java`
- `DeviceStorageStats.java`
- `FileTransferRequest.java` - Represents a single incoming file transfer request (file name + size in bytes). Includes `getFormattedSize()` for human-readable display.

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

Important files:

- `DeviceRepository.java` - Single source of truth for connection state, local device info, and remote PC info.
- `FileTransferRepository.java` - Single source of truth for the incoming file transfer lifecycle. Owns `LiveData<FileTransferRequest>` (the pending request) and `LiveData<FileTransferStatus>` (the current status). Also holds a `FileTransferActionListener` callback registered by `ConnectivityService` to bridge user decisions (Accept / Reject from the UI) to actual network writes without the ViewModel ever touching the transport layer.

Each repository is a Singleton focused on a single domain. Future features (clipboard, contacts) should each get their own repository rather than extending the existing ones.

The repository owns the observable app state used by the UI and is also updated by background services when connection events arrive.

## Services

Location:

```text
services/
```

Important files:

- `ConnectivityService.java` - Foreground service that owns the active PC connection.
- `AppNotificationManager.java` - Manages all app notifications: the persistent foreground service notification, the incoming file transfer heads-up notification (with Accept / Reject action buttons), and the send file progress / result notifications.
- `FileTransferActionReceiver.java` - `BroadcastReceiver` that handles Accept / Reject actions from the file transfer notification when the app is in the background. Calls directly into `FileTransferRepository` since `BroadcastReceiver` has no lifecycle and cannot hold a ViewModel reference.

`ConnectivityService` is responsible for:

- Creating the `TauSyncTransportManager`.
- Creating and configuring the `ChannelHandlerRegistry`.
- Registering all channel handlers.
- Connecting to the PC by IP.
- Sending initial Android device info after connection.
- Dispatching PC channel requests to the correct handler.
- Instantiating `RespondToFileTransferUseCase` and `ReceiveFileUseCase` and registering itself as the `FileTransferRepository.FileTransferActionListener`.
- Running the accept / reject network operations on a dedicated background thread (`FileTransferAcceptThread` / `FileTransferRejectThread`).
- Observing `SendFileRepository.getSendStatus()` via `observeForever` to drive send-file progress and result notifications without involving `MainActivity`.
- Cleaning up both `DeviceRepository` and `FileTransferRepository` state on disconnect.

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
- `FileDataChannelHandler.java` - Triggered by the polling loop when the PC opens `file_data_pc`. Calls `ReceiveFileUseCase` to stream the file bytes. Eliminates the simultaneous-connect race condition by letting the Desktop be the sole initiator of that channel.

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

## File Transfer Flow (PC → Android)

### Architecture

File transfer follows the same MVVM layers as connection management, with each layer having a single responsibility:

```text
Network Layer       FileMetadataChannelHandler
                        ↓  onTransferRequested()
Repository Layer    FileTransferRepository  (LiveData source of truth)
                        ↓  LiveData update
ViewModel Layer     FileTransferViewModel   (exposes state to UI)
                        ↓  observe
UI Layer            MainActivity            (Dialog / Notification)
```

The user's Accept / Reject decision travels back down through a callback:

```text
UI Layer            User taps Accept / Reject
                        ↓  acceptTransfer() / rejectTransfer()
ViewModel Layer     FileTransferViewModel
                        ↓  repository.onTransferAccepted/Rejected()
Repository Layer    FileTransferRepository  fires ActionListener callback
                        ↓
Service Layer       ConnectivityService.onUserAccepted(fileName)
                        ↓  background thread
Use Cases           RespondToFileTransferUseCase.accept()   → writes ACCEPT to PC
                    ReceiveFileUseCase.execute(fileName)    → reads bytes, saves to Downloads
```

The key design decision: `FileTransferViewModel` never touches `TransportManager` directly. `ConnectivityService` owns the transport and bridges user decisions to network operations via the `FileTransferActionListener` callback registered on `FileTransferRepository`.

### Step-by-step Flow

**1. PC sends file metadata**

The desktop opens the `file_meta_pc` TauSync channel and writes a JSON payload:

```json
{"file_name": "photo.jpg", "file_size": 4194304}
```

**2. Android detects and reads metadata**

The polling loop in `TauSyncTransportManager` calls `getPeerWaitingWords()` every 2 seconds. When `file_meta_pc` appears, `ChannelHandlerRegistry` routes it to `FileMetadataChannelHandler.onPeerRequest()`, which reads and parses the JSON. The parsed `FileTransferRequest` is pushed into `FileTransferRepository` → status becomes `PENDING_APPROVAL`.

**3. UI shows approval prompt**

`FileTransferViewModel` observes `FileTransferRepository.getPendingRequest()`. `MainActivity` observes the ViewModel:

- **App in foreground** → `AlertDialog` with file name, formatted size, and Accept / Reject buttons.
- **App in background** → heads-up notification (`FileTransferChannel`, high importance) with Accept and Reject action buttons handled by `FileTransferActionReceiver`.

**4. User accepts**

`FileTransferViewModel.acceptTransfer()` → `FileTransferRepository.onTransferAccepted()` → fires `FileTransferActionListener.onUserAccepted(fileName)` → `ConnectivityService` spawns `FileTransferAcceptThread`:

1. `RespondToFileTransferUseCase.accept()` writes `accept_android` to the `file_response_android` channel.
2. Android stops and waits. The Desktop receives ACCEPT, then opens `file_data_pc` alone.
3. The polling loop (every 2 s) detects `file_data_pc` in `getPeerWaitingWords()` → routes to `FileDataChannelHandler.onPeerRequest()`.
4. `ReceiveFileUseCase.execute(fileName)` streams bytes in 64 KB chunks from the TauSync `InputStream` directly into a MediaStore `OutputStream`. The full file is never held in RAM — safe for any file size.
5. File is saved to the public Downloads folder using `MediaStore.Downloads` (API 29+). No `WRITE_EXTERNAL_STORAGE` permission required.
6. `FileTransferRepository.onTransferCompleted()` → status becomes `COMPLETED` → MainActivity shows "File saved to Downloads ✓" Toast.

This polling-based approach eliminates the simultaneous-connect race condition that occurred when both sides called `connect("file_data_pc")` at the same time.

**4b. User rejects**

`FileTransferViewModel.rejectTransfer()` → `FileTransferRepository.onTransferRejected()` → fires `FileTransferActionListener.onUserRejected()` → `ConnectivityService` spawns `FileTransferRejectThread` → writes `reject_android` to `file_response_android`. The PC aborts without opening `file_data_pc`.

**5. Reset**

After any terminal status (COMPLETED / REJECTED / FAILED), `MainActivity` calls `fileTransferViewModel.reset()` which resets `FileTransferRepository` to `IDLE`, ready for the next transfer.

### TauSync Channels Used

| Channel enum | Wire value | Direction | Purpose |
|---|---|---|---|
| `REGULAR_FILE_METADATA_PC_TO_ANDROID` | `file_meta_pc` | PC → Android | JSON metadata (name + size) |
| `REGULAR_FILE_RESPONSE_FROM_ANDROID` | `file_response_android` | Android → PC | `accept_android` or `reject_android` |
| `REGULAR_FILE_DATA_PC_TO_ANDROID` | `file_data_pc` | PC → Android | Raw file bytes |

### FileTransferStatus lifecycle

```text
IDLE → PENDING_APPROVAL → RECEIVING → COMPLETED
                        ↘ REJECTED
             (any state) → FAILED
```

### New files added for this feature

```text
domain/entities/FileTransferRequest.java
domain/enums/FileTransferStatus.java
domain/usecases/RespondToFileTransferUseCase.java
domain/usecases/ReceiveFileUseCase.java
repositories/FileTransferRepository.java
viewmodel/FileTransferViewModel.java
network/handlers/FileMetadataChannelHandler.java
network/handlers/FileDataChannelHandler.java
services/FileTransferActionReceiver.java
```

---

## File Transfer Flow (Android → PC)

The user shares any file to SyncDose via Android's share sheet. `ShareReceiverActivity` (a transparent trampoline Activity) handles the `ACTION_SEND` Intent, delegates to `SendFileViewModel`, and immediately finishes — the app never comes to the foreground. Progress and results are shown as notifications driven by `ConnectivityService`.

### Architecture

```text
System          Android Share Sheet  (ACTION_SEND)
                    ↓
UI Layer        ShareReceiverActivity  (transparent, no UI, finish() immediately)
                    ↓  sendFile(uri, fileName)
ViewModel       SendFileViewModel
                    ↓  repository.requestSend(uri, fileName)
Repository      SendFileRepository  (LiveData source of truth)
                    ↓  ActionListener.onSendRequested(uri)
Service         ConnectivityService  ──observeForever──> AppNotificationManager
                    ↓  background thread
Use Case        SendFileUseCase.execute(uri, fileName)
```

### Step-by-step Flow

**1. User shares a file**

`ShareReceiverActivity` receives the `ACTION_SEND` Intent, checks `ConnectionStatus == CONNECTED`, resolves the file display name via `ContentResolver`, and calls `sendFileViewModel.sendFile(uri, fileName)`. It then calls `finish()` — the activity is gone and the app never appears on screen.

**2. Metadata sent to PC**

`SendFileUseCase` serializes `{name, size}` as JSON and writes it to the `file_meta_android` TauSync channel. Status → `WAITING_FOR_RESPONSE`. `ConnectivityService` observes the status change and shows a "Waiting for PC to accept…" progress notification.

**3. PC responds**

The PC's polling loop detects `file_meta_android`, shows a toast to the user, and writes `accept_pc` or `reject_pc` to the `file_response_pc` channel. `SendFileUseCase` reads the response with a 123-second timeout.

- **Accepted** → status → `SENDING`; notification updates to "Sending filename…"; use case streams file bytes to `file_data_android`.
- **Rejected** → status → `REJECTED`; result notification shown and auto-dismissed after 4 seconds.

**4. Transfer complete**

On success, status → `COMPLETED`. `ConnectivityService` shows a "File sent ✓" result notification (auto-dismissed after 4 seconds) and calls `SendFileRepository.reset()`.

### TauSync Channels Used

| Channel enum | Wire value | Direction | Purpose |
|---|---|---|---|
| `REGULAR_FILE_METADATA_ANDROID_TO_PC` | `file_meta_android` | Android → PC | JSON metadata (name + size) |
| `REGULAR_FILE_RESPONSE_FROM_PC` | `file_response_pc` | PC → Android | `accept_pc` or `reject_pc` |
| `REGULAR_FILE_DATA_ANDROID_TO_PC` | `file_data_android` | Android → PC | Raw file bytes |

### SendFileStatus lifecycle

```text
IDLE → WAITING_FOR_RESPONSE → SENDING → COMPLETED
                            ↘ REJECTED
              (any state)   → FAILED
```

### New files added for this feature

```text
domain/enums/SendFileStatus.java
domain/usecases/SendFileUseCase.java
repositories/SendFileRepository.java
viewmodel/SendFileViewModel.java
ui/ShareReceiverActivity.java
```

---

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

`NetworkHandler` exposes two read methods:
- `readFromChannel()` - returns `String` (UTF-8), used for text/JSON payloads.
- `readBytesFromChannel()` - returns raw `byte[]`, used for small binary data.

For file transfers, `TauSyncTransportManager.streamChannelToOutputStream()` is used instead — it pipes a TauSync `InputStream` into a MediaStore `OutputStream` in 64 KB chunks without buffering the full file in RAM.

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
- `FileTransferRepositoryTest.java` - Verifies all state-machine transitions (IDLE → PENDING_APPROVAL → RECEIVING → COMPLETED / REJECTED / FAILED → IDLE) and that `FileTransferActionListener` / `IncomingRequestListener` callbacks fire at the correct moments.
- `FileTransferViewModelTest.java` - Verifies that `acceptTransfer()`, `rejectTransfer()`, and `reset()` produce the expected LiveData state changes, and that `getPendingRequest()` / `getTransferStatus()` correctly reflect repository state.
- `SendFileRepositoryTest.java` - Verifies all state-machine transitions for the Android→PC send flow (IDLE → WAITING_FOR_RESPONSE → SENDING → COMPLETED / REJECTED / FAILED → IDLE) and that `SendFileActionListener` fires at the correct moments.
- `SendFileViewModelTest.java` - Verifies that `sendFile()` and `reset()` produce the expected LiveData state changes via the repository singleton.

Manual TauSync testing activities are under:

```text
testing/
```

These are useful for local protocol checks but are not part of the normal app flow.

## Requirements

* **Android Studio:** Panda 1 | 2025.3.1 Patch 1 or newer
* **JDK:** Java 21
* **Gradle:** 8.13
* **Min SDK:** 29 (Android 10.0)
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

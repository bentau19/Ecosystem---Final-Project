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
- `ShareReceiverActivity.java` - Invisible trampoline Activity for Android's share sheet (`ACTION_SEND`). Has no UI — it validates the intent, checks connection state, and forwards the file URI directly to `ConnectivityService` via a `startService()` Intent with `FLAG_GRANT_READ_URI_PERMISSION` (URI Intent Delegation). This is required to transfer the share-sheet URI grant from the Activity to the Service, since URI permissions are not automatically inherited by services. Calls `finish()` immediately. Not part of the Single Activity Architecture; acts as a system entry point (similar role to a `BroadcastReceiver`).
- `fragments/ConnectFragment.java` - Connection screen and QR flow.
- `fragments/ActionsFragment.java` - Main connected dashboard/actions screen.
- `fragments/BackupFragment.java` - Backup configuration and progress screen. Lets the user choose a backup mode (all media or a specific folder), configure options, start the transfer, and monitor progress via `BackupViewModel`.
- `fragments/FolderPickerFragment.java` - Bottom-sheet fragment for browsing and selecting a folder on the device filesystem. Used by `BackupFragment` to pick the source folder for folder-mode backups.
- `adapters/ToolsAdapter.java` - Adapter for action/tool items.
- `models/ToolItem.java` - UI model for dashboard tools.

## ViewModel Layer

Location:

```text
viewmodel/
```

Important files:

- `MainViewModel.java` - Coordinates connection state and user actions (QR scan, BLE discovery, hybrid connect, disconnect, refresh stats). Also owns the one-shot `justDisconnected` / `justDisconnectedByPc` flags that prevent `ConnectFragment.onResume` from auto-reconnecting after an intentional disconnect.
- `MainViewModelFactory.java` - Manual dependency creation for `MainViewModel`.
- `FileTransferViewModel.java` - Coordinates incoming file transfer state (PC → Android). Exposes `getPendingRequest()` and `getTransferStatus()` LiveData, and handles user Accept / Reject decisions.
- `BackupViewModel.java` - Coordinates the backup scan phase. Registers itself as `BackupRepository.ScanActionListener`, owns the background thread that runs `ScanBackupFilesUseCase`, and feeds results back to `BackupRepository`. Does not touch the network — the scan→transfer handoff is owned by the repository.
- `BackupViewModelFactory.java` - Manual dependency creation for `BackupViewModel`.

Each ViewModel is scoped to the host Activity and observed by the relevant Fragment or the Activity itself. ViewModels are split by feature to keep each one focused.

> **Note:** `SendFileViewModel` was removed. Outgoing file transfer (Android → PC) is driven entirely by `ShareReceiverActivity` → `ConnectivityService` → `SendFileRepository`, with no ViewModel in the path. Progress and results are exposed as notifications via `AppNotificationManager`.

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
- `PairWithPcUseCase.java` - Wraps BLE discovery and bonding. `discover()` scans for the PC's BLE beacon; `pair()` bonds with the found MAC and saves it for instant reconnect. `savedAddress()` / `savedPcName()` expose the remembered PC so `ConnectFragment.onResume` can skip scanning and connect directly.
- `DisconnectDeviceUseCase.java`
- `RefreshLocalStatsUseCase.java`
- `RespondToFileTransferUseCase.java` - Sends `ACCEPTED_FROM_ANDROID` or `REJECTED_FROM_ANDROID` to the PC over the response channel. Called by `ConnectivityService` on a background thread after the user decides.
- `ReceiveFileUseCase.java` - Streams file bytes from the `file_data_pc` TauSync channel directly into a MediaStore `OutputStream` in 64 KB chunks. The full file is never held in RAM, so arbitrarily large files are supported. Saves to the public Downloads folder using the MediaStore API (Android 10+, no storage permission required).
- `SendFileUseCase.java` - Serializes metadata and streams file bytes to the PC over the `file_data_android` TauSync channel.
- `ScanBackupFilesUseCase.java` - Enumerates files to back up. Supports two modes: `all_media` (images and videos via filesystem walk or MediaStore fallback) and `folder` (a user-selected SAF tree URI or filesystem path). Runs on a background thread; always synchronous.
- `BackupTransferUseCase.java` - Sends a scanned file list to the PC one file at a time over indexed TauSync slot channels (`backup_slot_meta_N` / `backup_slot_data_N`). Waits for per-file result confirmations from the PC (`backup_file_result_N`). Supports pause, resume, and stop mid-transfer.
- `VirtualDriveUseCase.java` - Handles all WinFsp filesystem operations forwarded by the desktop over TauSync (list, stat, read, write, create, delete, rename, truncate). Each method blocks on network I/O and must be called from a background thread.
- `ClipboardSyncUseCase.java` - Reads the current Android clipboard via `ClipboardManager`, serialises the text as `{"type":"text","content":"..."}`, and writes it to the `clipboard_android_to_pc` TauSync channel. Must be called from a background thread.

Current domain entities:

- `DeviceConnectionState.java`
- `LocalDeviceInfo.java`
- `RemoteDeviceInfo.java`
- `DeviceStorageStats.java`
- `ReceiveFileRequest.java` - Represents a single incoming file transfer request (file name + size in bytes). Includes `getFormattedSize()` for human-readable display.
- `BackupFileEntry.java` - Represents one file discovered during a backup scan (display path, size, modification time, source URI, relative path).
- `BackupOptions.java` - User-configured options for a backup run (e.g. whether to classify images by date).
- `VDriveEntry.java` - Metadata for a single virtual drive filesystem entry (name, size, modification time, whether it is a directory).
- `VDrivePageResult.java` - Paginated directory listing result (entries, has-more flag, next cursor).
- `VDriveReadRange.java` - Wraps a byte range read from a virtual drive file (offset, data).

## Data Layer

Location:

```text
data/datasource/
```

Important files:

- `SystemDataSource.java` - Reads Android system data such as device model, device ID, local IP, battery status, charging state, and storage stats.
- `BackupDataSource.java` - Platform I/O for backup file enumeration. Implements two scan strategies: SAF tree walk (`scanFolder`) and full-filesystem / MediaStore walk (`scanAllMedia`). Also handles post-transfer deletion of source files (`deleteSourceFile`) and cleanup of empty parent directories (`deleteEmptyParentFolders`).
- `VirtualDriveDataSource.java` - Implements the low-level filesystem operations that back the virtual drive: directory listing (with pagination), stat, ranged reads, streamed writes, create, delete, rename, and truncate. Operates on a local directory that mirrors the virtual drive tree visible to the desktop WinFsp mount.

This is the layer that talks directly to Android framework APIs.

## Repository Layer

Location:

```text
repositories/
```

Important files:

- `DeviceRepository.java` - Single source of truth for connection state, local device info, and remote PC info.
- `ReceiveFileRepository.java` - Single source of truth for the incoming file transfer lifecycle (PC → Android). Owns `LiveData<ReceiveFileRequest>` (the pending request) and `LiveData<ReceiveFileStatus>` (the current status). Also holds a `ReceiveFileActionListener` callback registered by `ConnectivityService` to bridge user decisions (Accept / Reject from the UI) to actual network writes without the ViewModel ever touching the transport layer.
- `SendFileRepository.java` - Single source of truth for the outgoing file transfer lifecycle (Android → PC). Owns `LiveData<SendFileStatus>` and a `SendFileActionListener` callback used by `ConnectivityService`.
- `BackupRepository.java` - Single source of truth for the backup scan and transfer lifecycle. Owns `LiveData<BackupScanStatus>`, `LiveData<BackupTransferStatus>`, and per-file progress counters. Bridges the scan→transfer handoff: when a scan completes, the repository automatically calls `requestTransfer()` using the options captured at scan time, so the Fragment that started the scan can navigate away immediately.
- `VirtualDriveRepository.java` - Thin singleton that delegates all virtual drive filesystem operations to `VirtualDriveDataSource`. Pure request/response — holds no observable state.

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
- `FileTransferActionReceiver.java` - `BroadcastReceiver` that handles Accept / Reject actions from the file transfer notification when the app is in the background. Calls directly into `ReceiveFileRepository` since `BroadcastReceiver` has no lifecycle and cannot hold a ViewModel reference.

`ConnectivityService` is responsible for:

- Creating the `TauSyncTransportManager`.
- Creating and configuring the `ChannelHandlerRegistry`.
- Registering all channel handlers.
- Connecting to the PC by IP.
- Sending initial Android device info after connection.
- Dispatching PC channel requests to the correct handler.
- Instantiating `RespondToFileTransferUseCase` and `ReceiveFileUseCase` and registering itself as the `ReceiveFileRepository.ReceiveFileActionListener`.
- Running the accept / reject network operations on a dedicated background thread (`FileTransferAcceptThread` / `FileTransferRejectThread`).
- Observing `SendFileRepository.getSendStatus()` via `observeForever` to drive send-file progress and result notifications without involving `MainActivity`.
- Registering as `BackupRepository.TransferActionListener` and `BackupRepository.ControlActionListener` to own the `BackupTransferUseCase` background thread and route pause / resume / stop commands to it.
- Cleaning up all repository state on disconnect.

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
- `ChannelHandlerRegistry.java` - Maps channel names to handlers. Supports prefix-based fallback routing for UUID-suffixed channels (used by VirtualDrive and Backup result channels).
- `DeviceInfoChannelHandler.java` - Generic handler for Android device info channels.
- `PCNameChannelHandler.java` - Reads the PC name and updates the repository.
- `DisconnectChannelHandler.java` - Handles PC-initiated disconnects.
- `FileMetadataChannelHandler.java` - Reads file metadata sent from the PC before a file transfer.
- `FileDataChannelHandler.java` - Triggered by the polling loop when the PC opens `file_data_pc`. Calls `ReceiveFileUseCase` to stream the file bytes. Eliminates the simultaneous-connect race condition by letting the Desktop be the sole initiator of that channel.
- `ClipboardFromPCHandler.java` - Triggered when the PC opens `clipboard_pc_to_android` (fired automatically on every PC clipboard change). Reads the JSON payload and sets the Android clipboard via `ClipboardManager`. Works in the background — Android allows clipboard writes without foreground restriction.
- `BackupControlChannelHandler.java` - Handles PC-originated backup control commands (`pause`, `resume`, `stop`) on the `backup_ctrl_pc` channel. Forwards each command to the running `BackupTransferUseCase`. One channel connect per command.
- `BackupReceivedChannelHandler.java` - Handles per-file transfer result tokens (`succ` / `fail`) sent by the PC on `backup_file_result_{slotIndex}` channels during an active backup session. Registered under the `BACKUP_FILE_RESULT` prefix; the registry's prefix-match fallback routes any slot-indexed channel here automatically.
- `VirtualDriveChannelHandler.java` - Handles a single op type (list, stat, read, write, create, delete, rename, truncate) for all UUID-suffixed virtual drive channels of that type. One instance is registered per op-type prefix; the registry routes every incoming UUID-suffixed channel to the matching instance.

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
- `BackupChannels.java` - TauSync meeting-word identifiers for the backup protocol: manifest, ready ack, per-file metadata slot, per-file data slot, per-file result, and bidirectional control channels.
- `BackupFileResult.java` - Per-file transfer result tokens (`succ` / `fail`) written by the PC on `BACKUP_FILE_RESULT` channels.
- `VirtualDriveChannels.java` - TauSync meeting-word base prefixes for the virtual drive protocol (list, stat, read, write, create, delete, rename, truncate, paginated list, full list). The PC appends a unique 8-char hex UUID to form the actual meeting word.
- `ClipboardChannels.java` — `CLIPBOARD_ANDROID_TO_PC` / `CLIPBOARD_PC_TO_ANDROID`

These files define the shared channel names used by both Android and desktop. Many of them are generated from the shared definitions under `shared/enums/`.

Avoid editing generated enum files manually. Change the shared source definitions and rerun code generation when possible.

## File Transfer Flow (PC → Android)

### Architecture

File transfer follows the same MVVM layers as connection management, with each layer having a single responsibility:

```text
Network Layer       FileMetadataChannelHandler
                        ↓  onTransferRequested()
Repository Layer    ReceiveFileRepository  (LiveData source of truth)
                        ↓  LiveData update
ViewModel Layer     FileTransferViewModel  (exposes state to UI)
                        ↓  observe
UI Layer            MainActivity           (Dialog / Notification)
```

The user's Accept / Reject decision travels back down through a callback:

```text
UI Layer            User taps Accept / Reject
                        ↓  acceptTransfer() / rejectTransfer()
ViewModel Layer     FileTransferViewModel
                        ↓  repository.onTransferAccepted/Rejected()
Repository Layer    ReceiveFileRepository  fires ReceiveFileActionListener callback
                        ↓
Service Layer       ConnectivityService.onUserAccepted(fileName)
                        ↓  background thread
Use Cases           RespondToFileTransferUseCase.accept()   → writes ACCEPT to PC
                    ReceiveFileUseCase.execute(fileName)    → reads bytes, saves to Downloads
```

The key design decision: `FileTransferViewModel` never touches `TransportManager` directly. `ConnectivityService` owns the transport and bridges user decisions to network operations via the `ReceiveFileActionListener` callback registered on `ReceiveFileRepository`.

### Step-by-step Flow

**1. PC sends file metadata**

The desktop opens the `file_meta_pc` TauSync channel and writes a JSON payload:

```json
{"file_name": "photo.jpg", "file_size": 4194304}
```

**2. Android detects and reads metadata**

The polling loop in `TauSyncTransportManager` calls `getPeerWaitingWords()` every 2 seconds. When `file_meta_pc` appears, `ChannelHandlerRegistry` routes it to `FileMetadataChannelHandler.onPeerRequest()`, which reads and parses the JSON. The parsed `ReceiveFileRequest` is pushed into `ReceiveFileRepository` → status becomes `PENDING_APPROVAL`.

**3. UI shows approval prompt**

`FileTransferViewModel` observes `ReceiveFileRepository.getPendingRequest()`. `MainActivity` observes the ViewModel:

- **App in foreground** → `AlertDialog` with file name, formatted size, and Accept / Reject buttons.
- **App in background** → heads-up notification (`FileTransferChannel`, high importance) with Accept and Reject action buttons handled by `FileTransferActionReceiver`.

**4. User accepts**

`FileTransferViewModel.acceptTransfer()` → `ReceiveFileRepository.onTransferAccepted()` → fires `ReceiveFileActionListener.onUserAccepted(fileName)` → `ConnectivityService` spawns `FileTransferAcceptThread`:

1. `RespondToFileTransferUseCase.accept()` writes `accept_android` to the `file_response_android` channel.
2. Android stops and waits. The Desktop receives ACCEPT, then opens `file_data_pc` alone.
3. The polling loop (every 2 s) detects `file_data_pc` in `getPeerWaitingWords()` → routes to `FileDataChannelHandler.onPeerRequest()`.
4. `ReceiveFileUseCase.execute(fileName)` streams bytes in 64 KB chunks from the TauSync `InputStream` directly into a MediaStore `OutputStream`. The full file is never held in RAM — safe for any file size.
5. File is saved to the public Downloads folder using `MediaStore.Downloads` (API 29+). No `WRITE_EXTERNAL_STORAGE` permission required.
6. `ReceiveFileRepository.onTransferCompleted()` → status becomes `COMPLETED` → MainActivity shows "File saved to Downloads ✓" Toast.

This polling-based approach eliminates the simultaneous-connect race condition that occurred when both sides called `connect("file_data_pc")` at the same time.

**4b. User rejects**

`FileTransferViewModel.rejectTransfer()` → `ReceiveFileRepository.onTransferRejected()` → fires `ReceiveFileActionListener.onUserRejected()` → `ConnectivityService` spawns `FileTransferRejectThread` → writes `reject_android` to `file_response_android`. The PC aborts without opening `file_data_pc`.

**5. Reset**

After any terminal status (COMPLETED / REJECTED / FAILED), `MainActivity` calls `fileTransferViewModel.reset()` which resets `ReceiveFileRepository` to `IDLE`, ready for the next transfer.

### TauSync Channels Used

| Channel enum | Wire value | Direction | Purpose |
|---|---|---|---|
| `REGULAR_FILE_METADATA_PC_TO_ANDROID` | `file_meta_pc` | PC → Android | JSON metadata (name + size) |
| `REGULAR_FILE_RESPONSE_FROM_ANDROID` | `file_response_android` | Android → PC | `accept_android` or `reject_android` |
| `REGULAR_FILE_DATA_PC_TO_ANDROID` | `file_data_pc` | PC → Android | Raw file bytes |

### ReceiveFileStatus lifecycle

```text
IDLE → PENDING_APPROVAL → RECEIVING → COMPLETED
                        ↘ REJECTED
             (any state) → FAILED
```

### New files added for this feature

```text
domain/entities/ReceiveFileRequest.java
domain/enums/ReceiveFileStatus.java
domain/usecases/RespondToFileTransferUseCase.java
domain/usecases/ReceiveFileUseCase.java
repositories/ReceiveFileRepository.java
viewmodel/FileTransferViewModel.java
network/handlers/FileMetadataChannelHandler.java
network/handlers/FileDataChannelHandler.java
services/FileTransferActionReceiver.java
```

---

## File Transfer Flow (Android → PC)

The user shares any file to SyncDose via Android's share sheet. `ShareReceiverActivity` (a transparent trampoline Activity) handles the `ACTION_SEND` Intent, delegates directly to `ConnectivityService` via a URI-delegating Intent, and immediately finishes — the app never comes to the foreground. Progress and results are shown as notifications driven by `ConnectivityService`.

### Architecture

```text
System          Android Share Sheet  (ACTION_SEND)
                    ↓
UI Layer        ShareReceiverActivity  (transparent, no UI, finish() immediately)
                    ↓  startService(ACTION_GRANT_FILE_URI + FLAG_GRANT_READ_URI_PERMISSION)
Service         ConnectivityService
                    ↓  SendFileRepository.requestSend(uri, fileName)
Repository      SendFileRepository  (LiveData source of truth)
                    ↓  ActionListener.onSendRequested(uri)
Service         ConnectivityService  ──observeForever──> AppNotificationManager
                    ↓  background thread
Use Case        SendFileUseCase.execute(uri)
```

`ShareReceiverActivity` bypasses any ViewModel. It uses `FLAG_GRANT_READ_URI_PERMISSION` on the `startService()` Intent to forward the share-sheet URI grant to the service — without this flag the service would receive a `SecurityException` when attempting to open the URI.

### Step-by-step Flow

**1. User shares a file**

`ShareReceiverActivity` receives the `ACTION_SEND` Intent, checks `ConnectionStatus == CONNECTED`, resolves the file display name via `ContentResolver`, then calls `startService()` with `ACTION_GRANT_FILE_URI`, the URI, the filename, and `FLAG_GRANT_READ_URI_PERMISSION`. It then calls `finish()` — the activity is gone and the app never appears on screen.

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
ui/ShareReceiverActivity.java
```

---

## Clipboard Sync

Two-directional clipboard sync between Android and the desktop PC.

### Android → PC

The user taps **"Send Clipboard to PC"** in the Actions screen. `ActionsFragment` reads the current clipboard via `ClipboardManager` before sending:

- If the clipboard is empty, a toast is shown and nothing is sent.
- If there is content, a preview toast shows the first 20 characters, the button switches to "Sent!" + checkmark and is disabled for 2 seconds, and `ClipboardSyncUseCase.execute()` is called on a background thread.

`ClipboardSyncUseCase` serialises the text as `{"type": "text", "content": "..."}` and writes it to the `clipboard_android_to_pc` TauSync channel.

### PC → Android

The desktop `ClipboardService` monitors clipboard changes automatically and pushes new content to the `clipboard_pc_to_android` channel. `ClipboardFromPCHandler` reads the payload and sets the Android clipboard.

### Anti-loop Guard

An SHA-256 hash of the last synced content is stored on the desktop. When the desktop receives text from Android and sets its own clipboard, the resulting clipboard-change event matches the stored hash and is silently dropped — preventing an echo send back to Android.

### TauSync Channels Used

| Channel enum | Wire value | Direction | Purpose |
|---|---|---|---|
| `CLIPBOARD_ANDROID_TO_PC` | `clipboard_android_to_pc` | Android → PC | User-initiated clipboard push |
| `CLIPBOARD_PC_TO_ANDROID` | `clipboard_pc_to_android` | PC → Android | Automatic desktop clipboard push |

### New files added for this feature

```text
enums/ClipboardChannels.java
domain/usecases/ClipboardSyncUseCase.java
network/handlers/ClipboardFromPCHandler.java
```

---

## Camera Mirror (Webcam Streaming)

Streams the phone camera to the PC as a virtual webcam over TauSync, so the phone can act as a high-quality webcam in video calls or OBS.

### Flow

1. The user navigates to the Camera Mirror screen. A live preview is shown immediately via CameraX `Preview`.
2. The user taps **Start Streaming**. `WebcamViewModel` transitions to `STREAMING` status.
3. A `CameraX ImageAnalysis` use case captures frames in `RGBA_8888` format, requesting 1280×720 (HD); devices that don't support that size fall back to the closest available resolution (e.g. 960×720).
4. Each frame is rotated to match the device's display orientation using `getRotationDegrees()`, compressed to JPEG at 70% quality, and pushed into `WebcamRepository.frameQueue`.
5. A 24 fps throttle gate ensures the send rate matches the desktop's `pyvirtualcam` consumption rate, preventing TCP buffer buildup and latency growth.
6. `WebcamStreamUseCase` reads frames from the queue and sends them over the `webcam_frames` TauSync channel using a 4-byte big-endian length prefix followed by the JPEG bytes.
7. On the desktop, `WebcamService` decodes each JPEG, pads it to 1280×720 preserving aspect ratio (pillarbox/letterbox), and pushes the frame to the OBS Virtual Camera via `pyvirtualcam`.

### Camera Selection

The **Flip Camera** button in the top-right corner of the screen toggles between the back camera (default) and the front camera without interrupting any active stream.

### Orientation

`MainActivity` declares `configChanges="orientation|screenSize|..."`, so rotation does not recreate the Activity and the stream is never interrupted. `WebcamFragment` instead re-inflates the orientation-appropriate layout in `onConfigurationChanged` — a stacked layout in portrait (`layout/fragment_webcam.xml`) and a side-by-side layout in landscape (`layout-land/fragment_webcam.xml`), where the preview fills the left region and the controls sit in a right-hand column so they never cover the viewfinder. The camera is rebound to the freshly-inflated `PreviewView`, refreshing the `ImageAnalysis` target rotation so the PC keeps receiving upright frames.

### TauSync Channels Used

| Channel enum | Wire value | Direction | Purpose |
|---|---|---|---|
| `WEBCAM_START` | `webcam_start` | Android → PC | Handshake — signals PC to open the virtual camera |
| `WEBCAM_FRAMES` | `webcam_frames` | Android → PC | Continuous JPEG frame stream (length-prefixed) |

### Frame Wire Format

```
[4 bytes big-endian uint32 = JPEG size][N bytes JPEG data]
```

### Prerequisites (Desktop)

The PC must have the **OBS Virtual Camera** driver installed (`OBS-VirtualCam` or bundled with OBS Studio). `pyvirtualcam` uses this driver to expose the phone's feed as a system webcam.

---

## Backup Flow (Android → PC)

The user taps Start Backup in `BackupFragment`, chooses a mode (all media or a specific folder), and optionally configures options (e.g. delete originals after transfer). The app scans the device for files, sends a manifest to the PC, waits for the PC user to confirm a destination folder, then streams every file to the PC over indexed TauSync slot channels.

### Architecture

```text
UI Layer        BackupFragment  (mode / options selection, progress display)
                    ↓  requestScan(mode, folderUri, options)
Repository      BackupRepository  (LiveData source of truth for scan + transfer)
                    ↓  ScanActionListener.onScanRequested()
ViewModel       BackupViewModel  (owns scan background thread)
                    ↓  ScanBackupFilesUseCase.execute()
DataSource      BackupDataSource  (filesystem / MediaStore enumeration)
                    ↓  onScanComplete(files) → repository auto-calls requestTransfer()
Service         ConnectivityService  (TransferActionListener)
                    ↓  background thread
Use Case        BackupTransferUseCase.execute(files, options)
                    ↓  backup_slot_meta_N / backup_slot_data_N channels
PC              Receives files, writes result to backup_file_result_N
                    ↓
Handler         BackupReceivedChannelHandler  → BackupRepository.onFileResult()
```

The PC can send pause / resume / stop commands at any point during the transfer via `BackupControlChannelHandler`.

### Step-by-step Flow

**1. Scan**

`BackupFragment` calls `BackupRepository.requestScan(mode, folderUri, options)`. The repository fires `ScanActionListener.onScanRequested()` → `BackupViewModel` spawns a background thread → `ScanBackupFilesUseCase` enumerates files using `BackupDataSource`. When complete, `BackupViewModel` calls `BackupRepository.onScanComplete(files)`.

**2. Scan → Transfer handoff**

`BackupRepository.onScanComplete()` automatically calls `requestTransfer(files, pendingOptions)` if the connection is still active. The `BackupFragment` has already returned to the main screen at this point — no UI involvement in the handoff.

**3. Manifest sent to PC**

`BackupTransferUseCase` sends `{num_files, total_size_bytes}` JSON on the `backup_manifest` channel. The PC displays a transfer summary and asks the user to confirm a destination folder.

**4. PC ready**

The PC writes `ready` on the `backup_ready_pc` channel. If the PC user cancels, a non-`ready` token is written and `BackupRepository.onTransferCanceledByPc()` is called — the app remains on `BackupFragment` and shows a Toast.

**5. File transfer loop**

For each file (slot index `i`):
1. Android sends `{name, size, mtime, rel_path}` JSON on `backup_slot_meta_{i}`.
2. Android streams raw bytes on `backup_slot_data_{i}`.
3. PC writes `succ` or `fail` on `backup_file_result_{i}`. `BackupReceivedChannelHandler` reads this and calls `BackupRepository.onFileResult()`.
4. If the user enabled "delete originals", `BackupDataSource.deleteSourceFile()` removes the source file on success.

**6. Completion**

`BackupRepository.onTransferComplete()` → `BackupTransferStatus.COMPLETED`. `ConnectivityService` shows a summary notification.

### TauSync Channels Used

| Channel enum | Wire value | Direction | Purpose |
|---|---|---|---|
| `BACKUP_MANIFEST_FROM_ANDROID` | `backup_manifest` | Android → PC | `{num_files, total_size_bytes}` header |
| `BACKUP_READY_FROM_PC` | `backup_ready_pc` | PC → Android | Ready ack / cancel token |
| `BACKUP_FILE_META_SLOT` | `backup_slot_meta_{i}` | Android → PC | Per-file JSON metadata |
| `BACKUP_FILE_DATA_SLOT` | `backup_slot_data_{i}` | Android → PC | Per-file raw bytes |
| `BACKUP_FILE_RESULT` | `backup_file_result_{i}` | PC → Android | `succ` or `fail` per file |
| `BACKUP_CONTROL_FROM_PC` | `backup_ctrl_pc` | PC → Android | `{"cmd":"pause"/"resume"/"stop"}` |
| `BACKUP_CONTROL_FROM_ANDROID` | `backup_ctrl_android` | Android → PC | `{"cmd":"pause"/"resume"/"stop"}` |

### BackupTransferStatus lifecycle

```text
IDLE → SENDING → COMPLETED
              ↘ PAUSED → SENDING (on resume)
              ↘ STOPPED
              ↘ FAILED
              ↘ CANCELED_BY_PC
```

### New files added for this feature

```text
data/datasource/BackupDataSource.java
domain/entities/BackupFileEntry.java
domain/entities/BackupOptions.java
domain/enums/BackupScanStatus.java
domain/enums/BackupTransferStatus.java
domain/usecases/ScanBackupFilesUseCase.java
domain/usecases/BackupTransferUseCase.java
enums/BackupChannels.java
enums/BackupFileResult.java
network/handlers/BackupControlChannelHandler.java
network/handlers/BackupReceivedChannelHandler.java
repositories/BackupRepository.java
ui/fragments/BackupFragment.java
ui/fragments/FolderPickerFragment.java
viewmodel/BackupViewModel.java
viewmodel/BackupViewModelFactory.java
```

---

## Virtual Drive Flow (PC → Android)

When the desktop mounts a connected phone as a Windows drive letter (via WinFsp), every filesystem operation the Windows shell issues — open, read, write, list directory, rename, delete, etc. — is forwarded over TauSync to the Android app. `VirtualDriveChannelHandler` routes each op to `VirtualDriveUseCase`, which delegates to `VirtualDriveDataSource` for the actual Android filesystem I/O. The result is sent back as a JSON response (or raw bytes for reads).

### Architecture

```text
PC (WinFsp / VirtualDrive.exe)
    ↓  connect("virtual_drive_{op}_{uuid8}")
TauSyncTransportManager  (polling loop detects UUID-suffixed meeting word)
    ↓
ChannelHandlerRegistry  (prefix-match routes to the correct handler instance)
    ↓
VirtualDriveChannelHandler.onPeerRequest(fullChannel)
    ↓
VirtualDriveUseCase.handle{Op}(fullChannel)
    ↓
VirtualDriveRepository  →  VirtualDriveDataSource  (filesystem I/O)
    ↓  JSON response / raw bytes
PC
```

No LiveData or ViewModel is involved — virtual drive ops are fully synchronous request/response on the `PeerRequestHandlerThread`.

### Channel routing

The PC appends a unique 8-character hex UUID to each base meeting word (e.g. `virtual_drive_list_a1b2c3d4`). Android registers one `VirtualDriveChannelHandler` instance per op-type under the base prefix; `ChannelHandlerRegistry`'s prefix-fallback routes every UUID-suffixed incoming word to the matching instance without requiring per-request handler registration.

### TauSync Channels Used

| Channel enum | Wire base | Op |
|---|---|---|
| `VIRTUAL_DRIVE_LIST` | `virtual_drive_list` | Directory listing |
| `VIRTUAL_DRIVE_LIST_PAGE` | `virtual_drive_list_page` | Paginated directory listing |
| `VIRTUAL_DRIVE_LIST_FULL` | `virtual_drive_list_full` | Full directory listing (cached by mtime) |
| `VIRTUAL_DRIVE_STAT` | `virtual_drive_stat` | File/directory metadata |
| `VIRTUAL_DRIVE_READ` | `virtual_drive_read` | Ranged file read (streams bytes) |
| `VIRTUAL_DRIVE_WRITE` | `virtual_drive_write` | File write (streams bytes in, then finalize) |
| `VIRTUAL_DRIVE_CREATE` | `virtual_drive_create` | Create file or directory |
| `VIRTUAL_DRIVE_DELETE` | `virtual_drive_delete` | Delete file or directory |
| `VIRTUAL_DRIVE_RENAME` | `virtual_drive_rename` | Rename / move |
| `VIRTUAL_DRIVE_TRUNCATE` | `virtual_drive_truncate` | Resize file |

### New files added for this feature

```text
data/datasource/VirtualDriveDataSource.java
domain/entities/VDriveEntry.java
domain/entities/VDrivePageResult.java
domain/entities/VDriveReadRange.java
domain/usecases/VirtualDriveUseCase.java
enums/VirtualDriveChannels.java
network/handlers/VirtualDriveChannelHandler.java
repositories/VirtualDriveRepository.java
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

- `DeviceRepositoryTest.java` - Covers connection state, battery/IP updates, `connectHybrid()` (BT path), and `justDisconnectedByPc` consume-once semantics.
- `DeviceSerializerTest.java`
- `MainViewModelTest.java` - Covers QR handling, hybrid connect, BLE discovery lifecycle (`startDiscovery`, `cancelDiscovery`), and `justDisconnected` / `justDisconnectedByPc` one-shot flags.
- `FileTransferRepositoryTest.java` - Verifies all state-machine transitions (IDLE → PENDING_APPROVAL → RECEIVING → COMPLETED / REJECTED / FAILED → IDLE) and that `FileTransferActionListener` / `IncomingRequestListener` callbacks fire at the correct moments.
- `FileTransferViewModelTest.java` - Verifies that `acceptTransfer()`, `rejectTransfer()`, and `reset()` produce the expected LiveData state changes, and that `getPendingRequest()` / `getTransferStatus()` correctly reflect repository state.
- `SendFileRepositoryTest.java` - Verifies all state-machine transitions for the Android→PC send flow (IDLE → WAITING_FOR_RESPONSE → SENDING → COMPLETED / REJECTED / FAILED → IDLE) and that `SendFileActionListener` fires at the correct moments.
- `BackupRepositoryTest.java` - Verifies the scan and transfer state-machine transitions, the scan→transfer auto-handoff logic, and the guard that discards stale scan results after a disconnect.
- `BackupViewModelTest.java` - Verifies that scan requests are routed to `ScanBackupFilesUseCase` on a background thread and that results are fed back to `BackupRepository` correctly.

Manual TauSync testing activities are under:

```text
testing/
```

These are useful for local protocol checks but are not part of the normal app flow.

## Requirements

* **Android Studio:** Panda 1 | 2025.3.1 Patch 1 or newer
* **JDK:** Java 21
* **Gradle:** 9.5.1
* **Min SDK:** 29 (Android 10.0)
* **Compile SDK:** 37
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

**5. Build & Run:** Deploy to a physical device or emulator (API 29+).


## Adding A New PC-Initiated Channel

Recommended process:

1. Add the channel to the shared enum definitions if it must be shared with desktop.
2. Regenerate Android and desktop enums.
3. Create a new class that implements `ChannelHandler`.
4. Register it in `ConnectivityService.registerChannelHandlers()`.
5. Keep all TauSync read/write logic inside the handler or transport layer.
6. Update tests if the handler contains meaningful logic.

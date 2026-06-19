# TauSync

A proprietary TCP multiplexing protocol that opens multiple independent named channels over a
single TCP connection. Both sides call `connect("channel_name")` with the same string (the
**meeting word**) and each receive a private full-duplex stream — no separate socket per channel.

**Protocol version:** 3.1 · **Port:** 8888

---

## Implementations

| Directory | Language | Role |
|---|---|---|
| [`Tausync_Windows/`](Tausync_Windows/TauSync.Lib/) | C# .NET 8 | Core library (`TauSync.Lib.dll`) compiled by Docker |
| [`windows/`](windows/README.md) | Python 3.9+ | `tausync_py` — Python wrapper around `TauSync.Lib.dll` via `pythonnet` |
| [`Tausync_Android/tausync-lib/`](Tausync_Android/tausync-lib/README.md) | Java (Android SDK 21+) | Native Java reimplementation for the Android companion app |

---

## TPack Frame Format

Every byte sent over the wire is wrapped in an 8-byte **TPack** header:

```
 0       1       2       3       4       5       6       7
 ├───────────────────────┤───────────────────┤───────────┤
 │    payload length     │    TargetID       │   flags   │
 │    (4B, LE uint32)    │  (3B, LE uint24)  │  (1B)     │
 └───────────────────────┴───────────────────┴───────────┘
```

- **Length** — number of payload bytes that follow (does not include the 8-byte header)
- **TargetID** — 24-bit channel ID assigned by the meeting-word handshake; `0` = control frame
- **Flags** — `0x01` = FIN (stream closing), other bits reserved

**Control frames** (TargetID = 0) carry JSON `TransferRequest` payloads with `MagicBytes = 0x54415553`.

---

## Meeting-Word Handshake

```
Client                          Server
  │   connect("device_info")      │
  │──────────── REQ ─────────────►│
  │                               │   connect("device_info")
  │◄─────────── ACK ──────────────│
  │                               │
  │◄═══ TauSyncStream (id=1) ════►│
```

1. The initiating side sends a `TransferRequest` with the meeting word over the control channel.
2. The remote side calls `connect()` with the same word and the protocol pairs them.
3. A monotonically incrementing 24-bit ID is assigned to the new channel (never reused within
   a session; stale FIN frames targeting unmapped IDs are dropped harmlessly).

Race resolution: if both sides open the same word simultaneously, the TCP server's perspective
wins as the authoritative channel ID.

---

## Channel Names Used in Ecosystem

Channel names are typed `StrEnum` / Java `enum` values — never raw string literals in app code.

| Enum class | Example wire value | Direction | Purpose |
|---|---|---|---|
| `DeviceInfoChannels` | `"device_name"`, `"battery"`, … | Android → PC | Per-field device metadata |
| `SessionChannels` | `"disconnect_from_phone"` | Android ↔ PC | Graceful disconnect signals |
| `FileTransferChannels` | `"file_meta_pc"`, `"file_data_pc"`, … | Bidirectional | File transfer handshake + data |
| `BackupChannels` | `"backup_control"`, … | Android → PC | Backup session control |

---

## Build

The C# library must be compiled before any Python or Android code that depends on it.

### With Docker (recommended — no local .NET required)

```bash
cd TauSync/
docker compose up
```

Output lands in `TauSync/windows/tausync_py/dll/`:

```
TauSync.Lib.dll        ← loaded by pythonnet at runtime
TauSync.Lib.deps.json
TauSync.Lib.pdb
```

### Without Docker

```bash
cd TauSync/Tausync_Windows/TauSync.Lib/
dotnet publish -c Release -o ../../../windows/tausync_py/dll/
```

---

## Further Reading

- **Python wrapper API:** [`windows/README.md`](windows/README.md)
- **Android SDK API:** [`Tausync_Android/tausync-lib/README.md`](Tausync_Android/tausync-lib/README.md)
- **Android integration tests:** [`Tausync_Android/tausync-lib/README_TESTS.md`](Tausync_Android/tausync-lib/README_TESTS.md)
- **Protocol spec:** [`Shared_Definitions/TauSync_Protocol_Spec.md`](Shared_Definitions/TauSync_Protocol_Spec.md)

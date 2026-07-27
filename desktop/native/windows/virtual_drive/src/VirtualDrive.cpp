#define NOMINMAX
#include <windows.h>
#include <sddl.h>   // ConvertStringSecurityDescriptorToSecurityDescriptorW

// winfsp.h is pulled in transitively by VirtualDrive.h, which also inserts
// the PNTSTATUS typedef that winfsp v2.0 requires.  Including it here before
// VirtualDrive.h would bypass that fix.
#include "VirtualDrive.h"
#include "WinFspUtil.h"
#include "PipeException.h"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cctype>
#include <cstring>
#include <future>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::json;

// Pipe name and buffer size come from Protocol.h so they stay in sync with main.cpp.

// ── Constants ─────────────────────────────────────────────────────────────────

// Volume label shown in Explorer's sidebar.
static constexpr wchar_t VOLUME_LABEL[] = L"Phone";

// Fallback total/free space (bytes) used only until SyncDose can report the
// connected device's real storage via the "volume" op (e.g. before the first
// device-info read completes, or when no phone is connected).
static constexpr uint64_t TOTAL_SIZE = 1ULL * 1024 * 1024 * 1024 * 1024; // 1 TB
static constexpr uint64_t FREE_SIZE  = 500ULL * 1024 * 1024 * 1024;      // 500 GB

// Sector / cluster geometry expected by WinFsp.
static constexpr uint16_t BYTES_PER_SECTOR    = 512;
static constexpr uint16_t SECTORS_PER_CLUSTER = 8;   // 4 KB clusters

// FspCleanupDelete / FspCleanupSetAllocationSize are enum values in winfsp.h.
// No local redefinitions needed.

// ── Helpers ───────────────────────────────────────────────────────────────────

// Build a self-relative security descriptor granting Everyone full access.
// WinFsp's GetSecurityByName / GetSecurity hand the raw descriptor bytes to the
// kernel, which requires a SELF-RELATIVE descriptor.  An absolute
// SECURITY_DESCRIPTOR copied verbatim fails kernel validation with
// ERROR_INVALID_SECURITY_DESCR (1338) — surfacing in Explorer as
// "The security descriptor structure is invalid" the moment root "/" is queried.
// ConvertStringSecurityDescriptorToSecurityDescriptorW returns a self-relative
// blob, which is exactly what the callbacks must return.
//   O:BA G:BA   owner/group = Administrators
//   D:P         protected DACL (no inheritance)
//   (A;;FA;;;WD) allow Full Access to Everyone (World)
// The descriptor is allocated once and intentionally leaked for process lifetime
// (matches the previous static pattern) — a single long-lived SD.
static PSECURITY_DESCRIPTOR MakeEveryoneFullSD()
{
    static PSECURITY_DESCRIPTOR sd = nullptr;
    if (!sd) {
        ConvertStringSecurityDescriptorToSecurityDescriptorW(
            L"O:BAG:BAD:P(A;;FA;;;WD)",
            SDDL_REVISION_1,
            &sd,
            nullptr);
    }
    return sd;
}

// ── VirtualDrive implementation ───────────────────────────────────────────────

VirtualDrive::VirtualDrive(std::vector<std::unique_ptr<ClientNamedPipe>> pipes)
    : _pipes(std::move(pipes))
{
    // Seed the free-list with every owned connection.
    for (auto& p : _pipes)
        _idle.push(p.get());
}

VirtualDrive::~VirtualDrive()
{
    // Mount() calls FspFileSystemStopDispatcher before returning, so by the
    // time the destructor runs the dispatcher is already stopped.
    if (_fs) {
        FspFileSystemDelete(_fs);
        _fs = nullptr;
    }
}

ClientNamedPipe* VirtualDrive::AcquirePipe()
{
    std::unique_lock<std::mutex> lk(_poolMtx);
    _poolCv.wait(lk, [this] { return !_idle.empty(); });
    ClientNamedPipe* p = _idle.front();
    _idle.pop();
    return p;
}

void VirtualDrive::ReleasePipe(ClientNamedPipe* pipe)
{
    {
        std::lock_guard<std::mutex> lk(_poolMtx);
        _idle.push(pipe);
    }
    _poolCv.notify_one();
}

// ── C++ metadata cache helpers ────────────────────────────────────────────────

void VirtualDrive::CacheStat(const std::string& path, const StatEntry& e)
{
    std::lock_guard<std::mutex> lk(_statMtx);
    _statCache[path] = e;
}

bool VirtualDrive::LookupStat(const std::string& path, StatEntry& out)
{
    std::lock_guard<std::mutex> lk(_statMtx);
    auto it = _statCache.find(path);
    if (it == _statCache.end()) return false;
    if (std::chrono::steady_clock::now() > it->second.expiry) {
        _statCache.erase(it);
        return false;
    }
    out = it->second;
    return true;
}

void VirtualDrive::InvalidateStat(const std::string& path)
{
    // Evict the path itself and its parent directory (parent listing changed).
    std::lock_guard<std::mutex> lk(_statMtx);
    _statCache.erase(path);
    auto slash = path.rfind('/');
    if (slash != std::string::npos && slash > 0)
        _statCache.erase(path.substr(0, slash));
    else if (slash == 0 && path.size() > 1)
        _statCache.erase("/");
}

protocol::Message VirtualDrive::SendReq(const std::string& json_str,
                                         const std::string& payload,
                                         std::chrono::milliseconds timeout)
{
    // Check out an idle connection so concurrent dispatcher threads each get
    // their own pipe — no global serialisation. The pool is sized to the
    // dispatcher thread count, so this rarely blocks.
    ClientNamedPipe* pipe = AcquirePipe();
    try {
        protocol::Message resp = protocol::send(*pipe, {json_str, payload}, timeout);
        ReleasePipe(pipe);
        return resp;
    } catch (const PipeException& e) {
        if (e.code == PipeErrorCode::ConnectionTimeout) {
            // SyncDose did not answer within the deadline. A late response may
            // still arrive, leaving the pipe byte-stream frame-desynced, so the
            // connection cannot be reused — swap in a fresh one (ReplacePipe).
            // The drive stays mounted and the op returns a retryable timeout;
            // STATUS_IO_TIMEOUT lets Windows re-issue the read.
            ReplacePipe(pipe);
            return protocol::Message{R"({"ok":false,"error":"timeout"})", ""};
        }
        // Genuine pipe break on ONE pooled connection. Do NOT tear down the whole
        // drive — a single broken/desynced pipe is recoverable. Swap it for a
        // fresh one (ReplacePipe) exactly like the timeout case, and return a
        // retryable error so Explorer surfaces a transient I/O error and retries
        // instead of the volume disappearing. ReplacePipe only signals _stopEvent
        // if SyncDose is genuinely unreachable (its whole pool is dead).
        ReplacePipe(pipe);
        return protocol::Message{R"({"ok":false,"error":"io_error"})", ""};
    } catch (...) {
        // Unknown failure on this connection — same recovery path as above.
        ReplacePipe(pipe);
        return protocol::Message{R"({"ok":false,"error":"io_error"})", ""};
    }
}

// Swap a frame-desynced (timed-out) pooled connection for a freshly opened one.
// The poisoned pipe was already removed from the idle free-list by AcquirePipe,
// so it lives only in _pipes; replacing its owning slot destroys (closes) it.
void VirtualDrive::ReplacePipe(ClientNamedPipe* poisoned)
{
    // Try to reconnect with a few short retries before giving up. A momentary
    // failure to reconnect (e.g. SyncDose's accept loop is briefly busy while
    // many pooled pipes recycle at once during a probe storm) must NOT be treated
    // as "SyncDose is gone" — otherwise a transient blip unmounts a healthy
    // drive. Only a sustained inability to reconnect should tear the drive down.
    std::unique_ptr<ClientNamedPipe> fresh;
    for (int attempt = 0; attempt < RECONNECT_ATTEMPTS; ++attempt) {
        try {
            fresh = std::make_unique<ClientNamedPipe>(
                protocol::PIPE_BUFFER_SIZE, protocol::PIPE_BUFFER_SIZE,
                protocol::PIPE_NAME_A, /*duplex=*/true);
            break;  // reconnected
        } catch (const PipeException&) {
            fresh.reset();
            if (attempt + 1 < RECONNECT_ATTEMPTS)
                Sleep(RECONNECT_BACKOFF_MS);
        }
    }

    std::lock_guard<std::mutex> lk(_poolMtx);
    for (auto& slot : _pipes) {
        if (slot.get() == poisoned) {
            slot = std::move(fresh);          // closes the poisoned connection
            if (slot) _idle.push(slot.get()); // re-arm the pool slot
            break;
        }
    }
    _poolCv.notify_one();

    // Only if reconnect failed after all retries AND the pool is now entirely
    // empty would AcquirePipe block forever — wake Mount() to tear down instead
    // of deadlocking. This is the sole self-stop trigger for SyncDose being gone.
    bool anyAlive = false;
    for (auto& slot : _pipes) {
        if (slot) { anyAlive = true; break; }
    }
    if (!anyAlive && _stopEvent) SetEvent(_stopEvent);
}

// static
void VirtualDrive::FillFileInfo(const FileNode& node, FSP_FSCTL_FILE_INFO* fi)
{
    std::memset(fi, 0, sizeof(*fi));
    fi->FileAttributes = node.is_dir
        ? FILE_ATTRIBUTE_DIRECTORY
        : FILE_ATTRIBUTE_NORMAL;
    fi->FileSize       = node.size;
    fi->AllocationSize = (node.size + 4095) & ~static_cast<uint64_t>(4095);
    UINT64 ft = MsToFileTime(node.mtime_ms);
    fi->CreationTime   = ft;
    fi->LastWriteTime  = ft;
    fi->LastAccessTime = ft;
    fi->ChangeTime     = ft;
}

// static
NTSTATUS VirtualDrive::ErrorToStatus(const std::string& error)
{
    if (error == "not_found")     return STATUS_OBJECT_NAME_NOT_FOUND;
    if (error == "access_denied") return STATUS_ACCESS_DENIED;
    // "not_connected" maps to a non-fatal I/O error, NOT STATUS_DEVICE_NOT_CONNECTED:
    // returning the device-removed status from a callback makes Windows unmount the
    // volume, so a brief connectivity blip would yank the drive. A genuine device
    // disconnect still unmounts cleanly via the Python device_disconnected →
    // VirtualDriveService.stop() path (which terminates this exe).
    if (error == "not_connected") return STATUS_IO_DEVICE_ERROR;
    if (error == "not_dir")       return STATUS_NOT_A_DIRECTORY;
    if (error == "exists")        return STATUS_OBJECT_NAME_COLLISION;
    if (error == "not_empty")     return STATUS_DIRECTORY_NOT_EMPTY;
    if (error == "timeout")       return STATUS_IO_TIMEOUT;
    return STATUS_IO_DEVICE_ERROR;
}

// Parse a pipe response body without ever throwing out of a WinFsp callback.
// SendReq always returns valid JSON on its own error paths, but a malformed or
// truncated frame must NOT escape as an uncaught exception — that would crash the
// dispatcher thread and unmount the drive. On failure the caller returns a
// non-fatal STATUS_IO_DEVICE_ERROR instead.
static bool TryParse(const std::string& body, json& out)
{
    try {
        out = json::parse(body);
        return true;
    } catch (...) {
        return false;
    }
}

// ── WinFsp interface vtable ───────────────────────────────────────────────────

// static
FSP_FILE_SYSTEM_INTERFACE VirtualDrive::MakeInterface()
{
    FSP_FILE_SYSTEM_INTERFACE iface = {};

    // Volume / Security
    iface.GetVolumeInfo     = GetVolumeInfo;
    iface.GetSecurityByName = GetSecurityByName;
    iface.GetSecurity       = GetSecurity;
    iface.SetSecurity       = SetSecurity;

    // Create
    iface.Create            = Create;
    iface.Open              = Open;
    iface.Overwrite         = Overwrite;

    // Read
    iface.Read              = Read;
    iface.ReadDirectory     = ReadDirectory;
    iface.GetFileInfo       = GetFileInfo;
    // Lets WinFsp answer a single-file directory query (FindFirstFile on an
    // exact name) from one stat instead of enumerating the whole directory.
    // Requires PassQueryDirectoryFileName, set in Mount.
    iface.GetDirInfoByName  = GetDirInfoByName;

    // Update
    iface.Write             = Write;
    iface.Flush             = Flush;
    iface.SetBasicInfo      = SetBasicInfo;
    iface.SetFileSize       = SetFileSize;
    iface.Rename            = Rename;

    // Delete
    iface.CanDelete         = CanDelete;
    iface.Cleanup           = Cleanup;
    iface.Close             = Close;

    return iface;
}

void VirtualDrive::Mount(const std::wstring& mountPoint)
{
    FSP_FSCTL_VOLUME_PARAMS params = {};
    params.SectorSize              = BYTES_PER_SECTOR;
    params.SectorsPerAllocationUnit= SECTORS_PER_CLUSTER;
    params.VolumeCreationTime      = 0;
    params.VolumeSerialNumber      = 0x53594E43; // "SYNC"
    params.FileInfoTimeout         = 30000;       // ms — trust FileInfo from ReadDirectory
                                                   // so WinFsp reuses listed metadata instead
                                                   // of re-stating every child on each access.
                                                   // Matches the 30 s C++ and Python cache TTLs.
    params.CaseSensitiveSearch     = 0;
    params.CasePreservedNames      = 1;
    params.UnicodeOnDisk           = 1;
    params.PersistentAcls          = 0;
    params.PostCleanupWhenModifiedOnly = 1;
    params.PassQueryDirectoryFileName = 1;
    params.UmFileContextIsUserContext2 = 1; // Use UserContext2 for file handles

    // Volume label
    std::wcsncpy(params.Prefix, L"", 1);
    std::wcsncpy(params.FileSystemName, L"PhoneFS", 8);

    FSP_FILE_SYSTEM_INTERFACE iface = MakeInterface();

    NTSTATUS st = FspFileSystemCreate(
        const_cast<PWSTR>(L"" FSP_FSCTL_DISK_DEVICE_NAME),
        &params,
        &iface,
        &_fs);

    if (!NT_SUCCESS(st))
        throw std::runtime_error("FspFileSystemCreate failed: " + std::to_string(st));

    _fs->UserContext = this;

    st = FspFileSystemSetMountPoint(_fs, const_cast<PWSTR>(mountPoint.c_str()));
    if (!NT_SUCCESS(st)) {
        FspFileSystemDelete(_fs);
        _fs = nullptr;
        throw std::runtime_error("FspFileSystemSetMountPoint failed: " + std::to_string(st));
    }

    // Create the stop-event BEFORE starting the dispatcher so that if SendReq
    // detects a pipe break on an early callback thread the SetEvent() null-guard
    // is never hit and the event is already there to be signalled.
    _stopEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!_stopEvent) {
        FspFileSystemDelete(_fs);
        _fs = nullptr;
        throw std::runtime_error("CreateEventW failed");
    }

    // Cap dispatcher threads to the connection-pool size so the number of
    // concurrent callers never exceeds available pipe connections (a caller
    // would otherwise block in AcquirePipe waiting for one to free up).
    st = FspFileSystemStartDispatcher(_fs, static_cast<ULONG>(_pipes.size()));
    if (!NT_SUCCESS(st)) {
        CloseHandle(_stopEvent);
        _stopEvent = nullptr;
        FspFileSystemDelete(_fs);
        _fs = nullptr;
        throw std::runtime_error("FspFileSystemStartDispatcher failed: " + std::to_string(st));
    }

    // Block until SendReq detects a pipe break and signals _stopEvent.
    // FspFileSystemWaitDispatcher was removed in WinFsp v2.0; we use a manual
    // event instead.  StopDispatcher must be called from this thread (not a
    // WinFsp callback thread) to avoid deadlock.
    WaitForSingleObject(_stopEvent, INFINITE);
    CloseHandle(_stopEvent);
    _stopEvent = nullptr;

    FspFileSystemStopDispatcher(_fs);
}

// ── WinFsp callbacks ─────────────────────────────────────────────────────────
// Organised by CRUD: Volume/Security → Create → Read → Update → Delete.

// ── Volume / Security ─────────────────────────────────────────────────────────

NTSTATUS VirtualDrive::GetVolumeInfo(FSP_FILE_SYSTEM* fs,
                                      FSP_FSCTL_VOLUME_INFO* vi)
{
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    std::memset(vi, 0, sizeof(*vi));

    // FSP_FSCTL_VOLUME_INFO.TotalSize / FreeSize are expressed in BYTES.
    // Default to the placeholder constants and override with the connected
    // device's real storage when SyncDose can supply it. The desktop answers
    // the "volume" op from its periodically-refreshed device-info snapshot.
    // We also cache the result for VOLUME_CACHE_TTL_S seconds at this layer so
    // Explorer's periodic sidebar refreshes cost zero named-pipe calls.
    uint64_t totalBytes = TOTAL_SIZE;
    uint64_t freeBytes  = FREE_SIZE;

    {
        std::lock_guard<std::mutex> lk(self->_volumeMtx);
        if (self->_volumeCache.has_value() &&
            std::chrono::steady_clock::now() < self->_volumeCache->expiry) {
            totalBytes = self->_volumeCache->total;
            freeBytes  = self->_volumeCache->free;
            vi->TotalSize  = totalBytes;
            vi->FreeSize   = freeBytes;
            std::wcsncpy(vi->VolumeLabel, VOLUME_LABEL,
                         sizeof(vi->VolumeLabel) / sizeof(wchar_t) - 1);
            vi->VolumeLabelLength =
                static_cast<UINT16>(std::wcslen(VOLUME_LABEL) * sizeof(wchar_t));
            return STATUS_SUCCESS;
        }
    }

    try {
        json req = {{"op", "volume"}};
        json j = json::parse(self->SendReq(req.dump()).json);
        if (j.value("ok", false)) {
            totalBytes = j.value("total", totalBytes);
            freeBytes  = j.value("free",  freeBytes);
            std::lock_guard<std::mutex> lk(self->_volumeMtx);
            self->_volumeCache = CachedVolume{
                totalBytes, freeBytes,
                std::chrono::steady_clock::now() + std::chrono::seconds(VOLUME_CACHE_TTL_S)
            };
        }
    } catch (...) {
        // Not connected yet or malformed response — keep the fallback constants.
    }

    vi->TotalSize  = totalBytes;
    vi->FreeSize   = freeBytes;
    std::wcsncpy(vi->VolumeLabel, VOLUME_LABEL, sizeof(vi->VolumeLabel) / sizeof(wchar_t) - 1);
    vi->VolumeLabelLength = static_cast<UINT16>(std::wcslen(VOLUME_LABEL) * sizeof(wchar_t));
    return STATUS_SUCCESS;
}

NTSTATUS VirtualDrive::GetSecurityByName(FSP_FILE_SYSTEM* fs,
                                          PWSTR FileName,
                                          PUINT32 PFileAttributes,
                                          PSECURITY_DESCRIPTOR SecurityDescriptor,
                                          SIZE_T* PSecurityDescriptorSize)
{
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    std::string path = WcharToUtf8(FileName);
    NormalizeVPath(path);

    // Check C++ stat cache first — ReadDirectory seeds it for all listed
    // entries, so the per-entry GetSecurityByName storm after a directory
    // open is usually answered without any named-pipe call.
    StatEntry cached{};
    if (!self->LookupStat(path, cached)) {
        json req = {{"op", "stat"}, {"path", path}};
        protocol::Message resp = self->SendReq(req.dump());
        json j;
        if (!TryParse(resp.json, j))
            return STATUS_IO_DEVICE_ERROR;
        if (!j.value("ok", false))
            return ErrorToStatus(j.value("error", "not_found"));
        cached = StatEntry{
            j.value("is_dir",   false),
            j.value("size",     uint64_t(0)),
            j.value("mtime_ms", uint64_t(0)),
            std::chrono::steady_clock::now() + std::chrono::seconds(STAT_CACHE_TTL_S)
        };
        self->CacheStat(path, cached);
    }

    if (PFileAttributes)
        *PFileAttributes = cached.is_dir
            ? FILE_ATTRIBUTE_DIRECTORY
            : FILE_ATTRIBUTE_NORMAL;

    // Return a minimal security descriptor so Explorer can open anything.
    if (PSecurityDescriptorSize) {
        PSECURITY_DESCRIPTOR sd = MakeEveryoneFullSD();
        DWORD sdSize = GetSecurityDescriptorLength(sd);
        if (SecurityDescriptor && *PSecurityDescriptorSize >= sdSize)
            std::memcpy(SecurityDescriptor, sd, sdSize);
        *PSecurityDescriptorSize = sdSize;
    }
    return STATUS_SUCCESS;
}

NTSTATUS VirtualDrive::GetSecurity(FSP_FILE_SYSTEM* /*fs*/,
                                    PVOID /*FileContext*/,
                                    PSECURITY_DESCRIPTOR SecurityDescriptor,
                                    SIZE_T* PSecurityDescriptorSize)
{
    PSECURITY_DESCRIPTOR sd = MakeEveryoneFullSD();
    DWORD sdSize = GetSecurityDescriptorLength(sd);
    if (SecurityDescriptor && *PSecurityDescriptorSize >= sdSize)
        std::memcpy(SecurityDescriptor, sd, sdSize);
    *PSecurityDescriptorSize = sdSize;
    return STATUS_SUCCESS;
}

NTSTATUS VirtualDrive::SetSecurity(FSP_FILE_SYSTEM* /*fs*/,
                                    PVOID /*FileContext*/,
                                    SECURITY_INFORMATION /*SecurityInformation*/,
                                    PSECURITY_DESCRIPTOR /*ModificationDescriptor*/)
{
    // Not supported — silently succeed.
    return STATUS_SUCCESS;
}

// ── Create ────────────────────────────────────────────────────────────────────

NTSTATUS VirtualDrive::Create(FSP_FILE_SYSTEM* fs,
                               PWSTR FileName,
                               UINT32 CreateOptions,
                               UINT32 GrantedAccess,
                               UINT32 FileAttributes,
                               PSECURITY_DESCRIPTOR SecurityDescriptor,
                               UINT64 AllocationSize,
                               PVOID* PFileContext,
                               FSP_FSCTL_FILE_INFO* FileInfo)
{
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    std::string path = WcharToUtf8(FileName);
    NormalizeVPath(path);
    bool is_dir = (FileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;

    json req = {{"op", "create"}, {"path", path}, {"is_dir", is_dir}};
    protocol::Message resp = self->SendReq(req.dump());
    json j;
    if (!TryParse(resp.json, j))
        return STATUS_IO_DEVICE_ERROR;

    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    // Evict parent's cached stat (its listing now includes the new entry).
    self->InvalidateStat(path);
    auto* node = new FileNode{path, is_dir, 0, 0, false};
    *PFileContext = node;
    FillFileInfo(*node, FileInfo);
    return STATUS_SUCCESS;
}

NTSTATUS VirtualDrive::Open(FSP_FILE_SYSTEM* fs,
                             PWSTR FileName,
                             UINT32 CreateOptions,
                             UINT32 GrantedAccess,
                             PVOID* PFileContext,
                             FSP_FSCTL_FILE_INFO* FileInfo)
{
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    std::string path = WcharToUtf8(FileName);
    NormalizeVPath(path);

    StatEntry cached{};
    if (!self->LookupStat(path, cached)) {
        json req = {{"op", "stat"}, {"path", path}};
        protocol::Message resp = self->SendReq(req.dump());
        json j;
        if (!TryParse(resp.json, j))
            return STATUS_IO_DEVICE_ERROR;
        if (!j.value("ok", false))
            return ErrorToStatus(j.value("error", "not_found"));
        cached = StatEntry{
            j.value("is_dir",   false),
            j.value("size",     uint64_t(0)),
            j.value("mtime_ms", uint64_t(0)),
            std::chrono::steady_clock::now() + std::chrono::seconds(STAT_CACHE_TTL_S)
        };
        self->CacheStat(path, cached);
    }

    auto* node = new FileNode{path, cached.is_dir, cached.size, cached.mtime_ms, false};
    // Streaming media gets a larger read window + prefetch-ahead (see Read).
    node->streaming = !cached.is_dir && IsStreamingPath(path);
    *PFileContext = node;
    FillFileInfo(*node, FileInfo);
    return STATUS_SUCCESS;
}

NTSTATUS VirtualDrive::Overwrite(FSP_FILE_SYSTEM* fs,
                                  PVOID FileContext,
                                  UINT32 FileAttributes,
                                  BOOLEAN ReplaceFileAttributes,
                                  UINT64 AllocationSize,
                                  FSP_FSCTL_FILE_INFO* FileInfo)
{
    // Treat overwrite as truncate to 0 then normal write flow.
    auto* node = static_cast<FileNode*>(FileContext);
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    json req = {{"op", "truncate"}, {"path", node->path}, {"new_size", 0}};
    protocol::Message resp = self->SendReq(req.dump());
    json j;
    if (!TryParse(resp.json, j))
        return STATUS_IO_DEVICE_ERROR;
    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    // File was truncated; cached size is now stale.
    self->InvalidateStat(node->path);
    node->size = 0;
    FillFileInfo(*node, FileInfo);
    return STATUS_SUCCESS;
}

// ── Read ──────────────────────────────────────────────────────────────────────

// Maximum read-ahead window for ordinary files. When a sequential read has
// fully ramped (see below) we ask Android for up to this many bytes per fetch.
// 8 MB reduces named-pipe round-trips by ~128× for sequential file copies
// (e.g. 64 KB WinFsp chunks × 128 = one round-trip per 8 MB of data).
static constexpr uint64_t READ_PREFETCH_BYTES = 8ULL * 1024 * 1024;

// ── Streaming pipeline tuning (video) ───────────────────────────────────────
// Streaming handles do NOT use the ramp below. Instead the foreground (player-
// blocking) read fetches at most FG_MAX so the first frame arrives fast, while a
// background pipeline keeps PREFETCH_DEPTH fixed-size STREAM_WINDOW windows
// buffered ahead of the read frontier. Pipelined small windows beat one giant
// window: each becomes usable as soon as it lands (not after a 100 MB blob), the
// pipeline refills continuously so the decoder never starves, and a foreground
// miss can wait at most ~one STREAM_WINDOW behind an in-flight prefetch.
// Memory per open video ≈ (PREFETCH_DEPTH + 1) × STREAM_WINDOW (current + ready).
static constexpr uint64_t STREAM_WINDOW  = 8ULL * 1024 * 1024;   // fixed prefetch window
static constexpr uint32_t PREFETCH_DEPTH = 3;                    // windows kept ahead
static constexpr uint64_t FG_MAX         = 1ULL * 1024 * 1024;   // foreground miss cap

// ── Sequential read-ahead ramp (NON-streaming files only) ───────────────────
// The window is NOT fixed: it starts small and doubles only while reads stay
// sequential. This distinguishes a hover/thumbnail read (a short, often
// non-sequential burst near the start — stays at the small window, fetching
// little) from a real file copy (sustained sequential reads — ramps up to the
// max window for throughput). WinFsp gives no reliable open-time "intent"
// signal, so the read *pattern* is the signal.
static constexpr uint64_t READ_WINDOW_MIN  = 256ULL * 1024;  // initial / hover window
static constexpr uint32_t READ_RAMP_MAX    = 5;  // 256 KB << 5 = 8 MB == READ_PREFETCH_BYTES

// Max read-ahead window for an ordinary (non-streaming) file. Streaming handles
// bypass this and use the STREAM_WINDOW pipeline instead.
static uint64_t MaxWindowFor(const FileNode* /*node*/)
{
    return READ_PREFETCH_BYTES;
}

// True if [Offset, Offset+len) is fully contained in cache window rc.
static bool CacheCovers(const FileNode::ReadCache& rc, uint64_t Offset, uint64_t len)
{
    uint64_t end = rc.startOffset + static_cast<uint64_t>(rc.data.size());
    return Offset >= rc.startOffset && (Offset + len) <= end;
}

bool VirtualDrive::IsStreamingPath(const std::string& path)
{
    size_t dot = path.find_last_of('.');
    if (dot == std::string::npos) return false;
    std::string ext = path.substr(dot + 1);
    for (char& c : ext)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return ext == "mp4" || ext == "mkv" || ext == "mov" || ext == "avi"
        || ext == "webm" || ext == "m4v" || ext == "ts" || ext == "m2ts";
}

bool VirtualDrive::EnsureReadSession(FileNode* node, std::unique_lock<std::mutex>& lk)
{
    if (!node->readSession.empty())
        return true;

    // Claim a slot before doing any I/O. Sessions are capped because each one
    // pins an Android peer-request thread for its lifetime; a handle that loses
    // the race just keeps using one-shot reads.
    int taken = _readSessionCount.fetch_add(1, std::memory_order_relaxed);
    if (taken >= MAX_READ_SESSIONS) {
        _readSessionCount.fetch_sub(1, std::memory_order_relaxed);
        return false;
    }

    // Capture the path before releasing the lock — Rename can retarget the node.
    std::string path = node->path;
    lk.unlock();
    json oreq = {{"op", "read_open"}, {"path", path}};
    protocol::Message ores = SendReq(oreq.dump(), {}, PIPE_READ_TIMEOUT);
    json oj;
    bool ok = TryParse(ores.json, oj) && oj.value("ok", false);
    std::string session = ok ? oj.value("session", "") : std::string{};
    lk.lock();

    if (session.empty()) {
        _readSessionCount.fetch_sub(1, std::memory_order_relaxed);
        return false;   // caller falls back to a one-shot fetch
    }

    if (node->readSession.empty()) {
        node->readSession = session;
        return true;
    }

    // A concurrent miss opened one first — close the duplicate so we don't leak
    // a TauSync channel on Android, and give back the slot we claimed.
    lk.unlock();
    json creq = {{"op", "read_close"}, {"session", session}};
    SendReq(creq.dump(), {}, PIPE_META_TIMEOUT);
    lk.lock();
    _readSessionCount.fetch_sub(1, std::memory_order_relaxed);
    return true;   // the handle does have a session, just not the one we opened
}

void VirtualDrive::DropReadSession(FileNode* node, std::unique_lock<std::mutex>& lk)
{
    if (node->readSession.empty())
        return;
    std::string session = std::move(node->readSession);
    node->readSession.clear();
    _readSessionCount.fetch_sub(1, std::memory_order_relaxed);

    lk.unlock();
    json creq = {{"op", "read_close"}, {"session", session}};
    SendReq(creq.dump(), {}, PIPE_META_TIMEOUT);
    lk.lock();
}

void VirtualDrive::PrefetchInto(FileNode* node, uint64_t start, uint64_t len, uint64_t gen)
{
    // Read the persistent session id under the lock (it may have been reopened).
    std::string session;
    {
        std::lock_guard<std::mutex> lk(node->readMtx);
        session = node->readSession;
    }
    if (session.empty()) return;  // no session — foreground read will fetch instead

    protocol::Message resp;
    bool ok = false;
    try {
        json req = {
            {"op", "read"}, {"session", session},
            {"offset", start}, {"length", len}
        };
        resp = SendReq(req.dump(), {}, PIPE_READ_TIMEOUT);
        ok = json::parse(resp.json).value("ok", false);
    } catch (...) {
        ok = false;  // prefetch is best-effort; the foreground read will retry
    }

    std::lock_guard<std::mutex> lk(node->readMtx);
    // Discard the result if the fetch failed or the player seeked away while it
    // was in flight (gen advanced) — RefillPipelineLocked relaunches from the
    // live frontier in that case.
    if (!ok || gen != node->prefetchGen || resp.payload.empty()) return;

    auto nc = std::make_unique<FileNode::ReadCache>();
    nc->startOffset = start;
    nc->data.assign(resp.payload.begin(), resp.payload.end());
    // Insert in ascending startOffset order, skipping an exact duplicate.
    auto it = node->ready.begin();
    while (it != node->ready.end() && (*it)->startOffset < start) ++it;
    if (it == node->ready.end() || (*it)->startOffset != start)
        node->ready.insert(it, std::move(nc));
}

void VirtualDrive::RefillPipelineLocked(FileNode* node, uint64_t frontier)
{
    if (!node->streaming || node->readSession.empty()) return;

    // 1. Prune completed prefetch slots. Their results (if still current) were
    //    already inserted into `ready` by PrefetchInto; stale-gen results were
    //    discarded there. get() never blocks here (the future is ready).
    for (auto it = node->prefetch.begin(); it != node->prefetch.end(); ) {
        if (it->fut.valid() &&
            it->fut.wait_for(std::chrono::seconds(0)) == std::future_status::ready) {
            try { it->fut.get(); } catch (...) {}
            it = node->prefetch.erase(it);
        } else {
            ++it;
        }
    }

    // 2. Drop ready windows entirely behind the read frontier (consumed/seeked past).
    while (!node->ready.empty()) {
        const auto& rc = *node->ready.front();
        if (rc.startOffset + rc.data.size() <= frontier) node->ready.pop_front();
        else break;
    }

    // 3. Count in-flight prefetches for the CURRENT generation. Stale in-flight
    //    slots (old gen, from before a seek) are ignored so a seek refills now.
    size_t inflight = 0;
    for (const auto& slot : node->prefetch)
        if (slot.gen == node->prefetchGen) ++inflight;

    // 4. Launch AT MOST ONE prefetch at a time. The persistent session stream is
    //    serial (the Python side serialises request/response on it), so concurrent
    //    fetches would only contend on that lock and add head-of-line latency to a
    //    foreground miss. One-at-a-time has the same throughput while bounding a
    //    foreground miss's wait behind an in-flight prefetch to a single window.
    //    The ready buffer is filled toward PREFETCH_DEPTH across successive reads:
    //    each completed prefetch lets the next read launch the following window.
    if (inflight == 0 &&
        node->ready.size() < PREFETCH_DEPTH &&
        node->prefetchFrontier < node->size) {
        uint64_t start = node->prefetchFrontier;
        uint64_t len   = std::min<uint64_t>(STREAM_WINDOW, node->size - start);
        uint64_t gen   = node->prefetchGen;
        try {
            node->prefetch.push_back(FileNode::PrefetchSlot{
                start, gen,
                std::async(std::launch::async,
                    [this, node, start, len, gen]() { PrefetchInto(node, start, len, gen); })
            });
            node->prefetchFrontier += len;
        } catch (...) {
            // Thread/resource exhaustion — try again on the next read. Never let
            // this escape into the WinFsp callback.
        }
    }
}

NTSTATUS VirtualDrive::Read(FSP_FILE_SYSTEM* fs,
                             PVOID FileContext,
                             PVOID Buffer,
                             UINT64 Offset,
                             ULONG Length,
                             PULONG PBytesTransferred)
{
    auto* node = static_cast<FileNode*>(FileContext);
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    // Clamp length to what the file actually has.
    if (Offset >= node->size) {
        *PBytesTransferred = 0;
        return STATUS_END_OF_FILE;
    }
    ULONG actual = static_cast<ULONG>(
        std::min(static_cast<uint64_t>(Length), node->size - Offset));

    std::unique_lock<std::mutex> lk(node->readMtx);

    // ── Current window hit ─────────────────────────────────────────────────
    if (node->readCache && CacheCovers(*node->readCache, Offset, actual)) {
        size_t idx = static_cast<size_t>(Offset - node->readCache->startOffset);
        std::memcpy(Buffer, node->readCache->data.data() + idx, actual);
        *PBytesTransferred = actual;
        if (node->streaming)
            self->RefillPipelineLocked(
                node, node->readCache->startOffset + node->readCache->data.size());
        return STATUS_SUCCESS;
    }

    // ── Prefetched window hit: promote it to current and serve ──────────────
    // `ready` is only ever populated for streaming handles; the loop is a no-op
    // (empty deque) for ordinary files.
    for (size_t i = 0; i < node->ready.size(); ++i) {
        if (!CacheCovers(*node->ready[i], Offset, actual)) continue;
        // Drop any earlier windows the player has now advanced past.
        for (size_t k = 0; k < i; ++k) node->ready.pop_front();
        node->readCache = std::move(node->ready.front());
        node->ready.pop_front();
        size_t idx = static_cast<size_t>(Offset - node->readCache->startOffset);
        std::memcpy(Buffer, node->readCache->data.data() + idx, actual);
        *PBytesTransferred = actual;
        self->RefillPipelineLocked(
            node, node->readCache->startOffset + node->readCache->data.size());
        return STATUS_SUCCESS;
    }

    // ── Streaming miss: small foreground fetch + background pipeline refill ──
    if (node->streaming) {
        // Lazily open the persistent read session on the first miss so a handle
        // that is opened but barely read (e.g. a thumbnailer) pays nothing.
        // If no session slot is free this returns false and the fetch below
        // degrades to a one-shot channel rather than failing the read; the
        // background prefetch pipeline also no-ops without a session.
        bool haveSession = self->EnsureReadSession(node, lk);

        // Seek detection: an offset before the current window, or beyond the
        // prefetch frontier, means the player jumped — bump the generation (so
        // stale in-flight windows are discarded on arrival) and reset the
        // pipeline. A miss inside the queued span is mere starvation; keep the
        // in-flight windows so they are not refetched.
        bool seek = node->readCache &&
            (Offset < node->readCache->startOffset || Offset > node->prefetchFrontier);
        if (seek) {
            ++node->prefetchGen;
            node->ready.clear();
            node->prefetchFrontier = 0;
        }

        std::string session = node->readSession;
        // FG_MAX caps the player-blocking read so the first frame arrives fast;
        // everything beyond it is read ahead in the background by the pipeline.
        uint64_t fgLen = std::min<uint64_t>(
            std::max<uint64_t>(static_cast<uint64_t>(actual), FG_MAX),
            node->size - Offset);
        // Capture the path before releasing the lock — Rename can retarget the node.
        std::string path = node->path;
        lk.unlock();

        // Without a session (pool exhausted) fall back to a one-shot fetch on the
        // same wire protocol — SyncDose opens and closes a channel for it.
        json req = haveSession
            ? json{{"op", "read"}, {"session", session},
                   {"offset", Offset}, {"length", fgLen}}
            : json{{"op", "read"}, {"path", path},
                   {"offset", Offset}, {"length", fgLen}};
        protocol::Message resp = self->SendReq(req.dump(), {},
                                               VirtualDrive::PIPE_READ_TIMEOUT);

        // Tear the session down on any failure: close it (so SyncDose drops the
        // stream and Android's read loop unblocks via EOF) and clear the id so the
        // next miss reopens a fresh session. Reopening is cheap and keeps the
        // failure handling uniform; a playing video almost never hits this path.
        auto poison = [&]() {
            lk.lock();
            if (node->readSession == session)
                self->DropReadSession(node, lk);
        };

        json j;
        if (!TryParse(resp.json, j)) {
            poison();
            return STATUS_IO_DEVICE_ERROR;
        }
        if (!j.value("ok", false)) {
            std::string err = j.value("error", "");
            poison();
            return ErrorToStatus(err);
        }

        ULONG received = static_cast<ULONG>(
            std::min<uint64_t>(resp.payload.size(), static_cast<uint64_t>(actual)));
        std::memcpy(Buffer, resp.payload.data(), received);
        *PBytesTransferred = received;

        lk.lock();
        auto rc = std::make_unique<FileNode::ReadCache>();
        rc->startOffset = Offset;
        rc->data.assign(resp.payload.begin(), resp.payload.end());
        uint64_t winEnd = Offset + rc->data.size();
        node->readCache = std::move(rc);
        // Advance (never rewind) the prefetch frontier so the pipeline continues
        // right after the foreground window without refetching in-flight windows.
        node->prefetchFrontier = std::max(node->prefetchFrontier, winEnd);
        self->RefillPipelineLocked(node, winEnd);
        return STATUS_SUCCESS;
    }

    // ── Non-streaming miss: adaptive ramp, one synchronous window fetch ──────
    // A miss that continues exactly where the last fetch ended is a sustained
    // sequential read (file copy) → ramp the window up; anything else (first read
    // of a handle, or a seek) resets the ramp, so a hover fetches just
    // READ_WINDOW_MIN instead of the full max.
    bool sequential = (node->lastFetchEnd != 0 && Offset == node->lastFetchEnd);
    node->rampStep = sequential ? std::min(node->rampStep + 1, READ_RAMP_MAX) : 0;
    uint64_t window = std::min<uint64_t>(READ_WINDOW_MIN << node->rampStep, MaxWindowFor(node));

    // Once the ramp proves this is a sustained sequential read (a copy, not a
    // hover or thumbnail), promote the handle to a persistent session so the
    // remaining windows skip the per-window channel handshake and file reopen.
    // An already-open session is always reused — a seek resets the ramp but must
    // not abandon the channel. Below the threshold, and when no session slot is
    // free, reads stay one-shot.
    bool haveSession = !node->readSession.empty();
    if (!haveSession && node->rampStep >= SESSION_RAMP_MIN)
        haveSession = self->EnsureReadSession(node, lk);
    std::string session = node->readSession;

    // Release readMtx during the blocking pipe round-trip so a concurrent Read is
    // not stalled behind it. Clamp to EOF. Capture the path first — Rename can
    // retarget the node once the lock is dropped.
    uint64_t fetchLen = std::min<uint64_t>(
        std::max<uint64_t>(static_cast<uint64_t>(actual), window),
        node->size - Offset);
    std::string path = node->path;
    lk.unlock();

    json req = haveSession
        ? json{{"op", "read"}, {"session", session},
               {"offset", Offset}, {"length", fetchLen}}
        : json{{"op", "read"}, {"path", path},
               {"offset", Offset}, {"length", fetchLen}};
    protocol::Message resp = self->SendReq(req.dump(), {},
                                           VirtualDrive::PIPE_READ_TIMEOUT);
    json j;
    bool parsed = TryParse(resp.json, j);
    if (!parsed || !j.value("ok", false)) {
        // Drop a failed session so the next read reopens one (or falls back to a
        // one-shot fetch); a one-shot failure needs no teardown.
        if (haveSession) {
            lk.lock();
            if (node->readSession == session)
                self->DropReadSession(node, lk);
            lk.unlock();
        }
        if (!parsed)
            return STATUS_IO_DEVICE_ERROR;
        return ErrorToStatus(j.value("error", ""));
    }

    ULONG received = static_cast<ULONG>(
        std::min<uint64_t>(resp.payload.size(), static_cast<uint64_t>(actual)));
    std::memcpy(Buffer, resp.payload.data(), received);
    *PBytesTransferred = received;

    // Install the fetched chunk as the current window.
    lk.lock();
    auto rc = std::make_unique<FileNode::ReadCache>();
    rc->startOffset = Offset;
    rc->data.assign(resp.payload.begin(), resp.payload.end());
    node->readCache = std::move(rc);
    // Advance the sequential-fetch frontier so the next contiguous miss is seen
    // as sequential and keeps ramping the window.
    node->lastFetchEnd = std::max(node->lastFetchEnd,
                                  Offset + node->readCache->data.size());
    return STATUS_SUCCESS;
}

// Entries requested per "list_page" op while filling the directory buffer.
// SyncDose answers every page of one enumeration out of its own cached listing,
// so these are local named-pipe hops (microseconds), not trips to the phone —
// 500 keeps the JSON per hop modest while halving the number of hops.
static constexpr int LIST_PAGE_SIZE = 500;

// Build one FSP_FSCTL_DIR_INFO for `name` into `scratch` and return it.
//
// Size deliberately EXCLUDES the terminating NUL. WinFsp derives the name
// length as (Size - sizeof(FSP_FSCTL_DIR_INFO)) / sizeof(WCHAR), so counting the
// NUL appends a phantom character to every filename — which corrupts the
// directory buffer's sort and makes its marker binary search never find an
// exact match, re-emitting the directory from the start on every continuation.
static FSP_FSCTL_DIR_INFO* BuildDirInfo(std::vector<uint8_t>& scratch,
                                        const std::wstring& name,
                                        bool is_dir,
                                        uint64_t size,
                                        uint64_t mtime_ms)
{
    size_t total = sizeof(FSP_FSCTL_DIR_INFO) + name.size() * sizeof(wchar_t);
    scratch.assign(total, 0);
    auto* di = reinterpret_cast<FSP_FSCTL_DIR_INFO*>(scratch.data());

    di->Size = static_cast<UINT16>(total);
    UINT64 ft = MsToFileTime(mtime_ms);
    di->FileInfo.FileAttributes = is_dir ? FILE_ATTRIBUTE_DIRECTORY
                                         : FILE_ATTRIBUTE_NORMAL;
    di->FileInfo.FileSize       = is_dir ? 0 : size;
    di->FileInfo.AllocationSize = (di->FileInfo.FileSize + 4095) & ~uint64_t(4095);
    di->FileInfo.CreationTime   = ft;
    di->FileInfo.LastWriteTime  = ft;
    di->FileInfo.LastAccessTime = ft;
    di->FileInfo.ChangeTime     = ft;
    std::memcpy(di->FileNameBuf, name.c_str(), name.size() * sizeof(wchar_t));
    return di;
}

NTSTATUS VirtualDrive::ReadDirectory(FSP_FILE_SYSTEM* fs,
                                      PVOID FileContext,
                                      PWSTR Pattern,
                                      PWSTR Marker,
                                      PVOID Buffer,
                                      ULONG Length,
                                      PULONG PBytesTransferred)
{
    auto* node = static_cast<FileNode*>(FileContext);
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    // Pattern is intentionally unused: the FSD filters user-mode results itself.
    // PassQueryDirectoryFileName only forwards it as a hint, and the callback
    // that actually exploits it is GetDirInfoByName (see MakeInterface).
    (void)Pattern;

    // ── Stat-cache seeding helper ──────────────────────────────────────────
    // Seed the class-level C++ stat cache from every freshly fetched page so
    // that the GetSecurityByName / Open stat storm WinFsp issues right after
    // a directory open is answered without any additional named-pipe call.
    auto seedStatCache = [&](const std::vector<json>& entries) {
        auto seedExpiry = std::chrono::steady_clock::now()
                        + std::chrono::seconds(STAT_CACHE_TTL_S);
        for (const auto& entry : entries) {
            std::string name = entry.value("name", "");
            if (name.empty()) continue;
            std::string childPath = (node->path == "/")
                ? "/" + name
                : node->path + "/" + name;
            self->CacheStat(childPath, StatEntry{
                entry.value("is_dir",   false),
                entry.value("size",     uint64_t(0)),
                entry.value("mtime_ms", uint64_t(0)),
                seedExpiry
            });
        }
    };

    // ── Fill the directory buffer (first call, or after WinFsp restarts) ─────
    // Acquire returns TRUE only when this thread must do the filling; a
    // concurrent ReadDirectory on the same handle blocks inside it until the
    // fill completes. Reset = (Marker == nullptr) discards a stale or
    // half-filled buffer when WinFsp restarts the scan from the beginning.
    NTSTATUS result = STATUS_SUCCESS;
    if (FspFileSystemAcquireDirectoryBuffer(&node->dirBuffer,
                                            static_cast<BOOLEAN>(nullptr == Marker),
                                            &result)) {
        std::string after;
        bool hasMore = true;
        std::vector<uint8_t> scratch;   // reused staging buffer for one DIR_INFO

        while (hasMore && NT_SUCCESS(result)) {
            json req = {
                {"op",    "list_page"},
                {"path",  node->path},
                {"after", after.empty() ? json(nullptr) : json(after)},
                {"limit", LIST_PAGE_SIZE}
            };
            protocol::Message resp = self->SendReq(req.dump(), {}, PIPE_LIST_TIMEOUT);
            json j;
            if (!TryParse(resp.json, j)) {
                result = STATUS_IO_DEVICE_ERROR;
                break;
            }
            if (!j.value("ok", false)) {
                result = ErrorToStatus(j.value("error", ""));
                break;
            }

            auto entries = j["entries"].get<std::vector<json>>();
            seedStatCache(entries);

            for (const auto& entry : entries) {
                std::string name = entry.value("name", "");
                if (name.empty()) continue;
                auto* di = BuildDirInfo(
                    scratch,
                    Utf8ToWchar(name),
                    entry.value("is_dir",   false),
                    entry.value("size",     uint64_t(0)),
                    entry.value("mtime_ms", uint64_t(0)));
                if (!FspFileSystemFillDirectoryBuffer(&node->dirBuffer, di, &result))
                    break;   // `result` carries the reason
            }

            // Guard a peer that claims has_more but returns nothing.
            if (entries.empty()) break;

            hasMore = j.value("has_more", false);
            after   = j.value("next_after", "");
        }

        // Sorts the buffer and releases the fill lock. Must run on every path
        // out of the fill, including failure — otherwise concurrent readers
        // block forever.
        FspFileSystemReleaseDirectoryBuffer(&node->dirBuffer);
    }

    if (!NT_SUCCESS(result))
        return result;

    // WinFsp serves this and every continuation from the buffer: it owns the
    // marker search and emits the end-of-directory marker itself.
    FspFileSystemReadDirectoryBuffer(&node->dirBuffer, Marker,
                                     Buffer, Length, PBytesTransferred);
    return STATUS_SUCCESS;
}

NTSTATUS VirtualDrive::GetDirInfoByName(FSP_FILE_SYSTEM* fs,
                                         PVOID FileContext,
                                         PWSTR FileName,
                                         FSP_FSCTL_DIR_INFO* DirInfo)
{
    auto* node = static_cast<FileNode*>(FileContext);
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    // FileName is a single path component relative to the open directory.
    std::string name = WcharToUtf8(FileName);
    std::string childPath = (node->path == "/")
        ? "/" + name
        : node->path + "/" + name;
    NormalizeVPath(childPath);

    // Almost always a cache hit: ReadDirectory seeds every listed child, and a
    // preceding Open/GetSecurityByName seeds the rest.
    StatEntry cached{};
    if (!self->LookupStat(childPath, cached)) {
        json req = {{"op", "stat"}, {"path", childPath}};
        protocol::Message resp = self->SendReq(req.dump());
        json j;
        if (!TryParse(resp.json, j))
            return STATUS_IO_DEVICE_ERROR;
        if (!j.value("ok", false))
            return ErrorToStatus(j.value("error", "not_found"));
        cached = StatEntry{
            j.value("is_dir",   false),
            j.value("size",     uint64_t(0)),
            j.value("mtime_ms", uint64_t(0)),
            std::chrono::steady_clock::now() + std::chrono::seconds(STAT_CACHE_TTL_S)
        };
        self->CacheStat(childPath, cached);
    }

    // WinFsp's DirInfo buffer holds at most 255 WCHARs of name
    // (FspFileSystemOpQueryDirectory_GetDirInfoByName). A legal Windows path
    // component always fits, but the name came from the phone — bound it rather
    // than trust it, or a malformed response would overrun the FSD's stack buffer.
    std::wstring wname = Utf8ToWchar(name);
    if (wname.empty() || wname.size() > 255)
        return STATUS_OBJECT_NAME_INVALID;

    std::memset(DirInfo, 0, sizeof(*DirInfo));
    DirInfo->Size = static_cast<UINT16>(
        sizeof(FSP_FSCTL_DIR_INFO) + wname.size() * sizeof(wchar_t));
    UINT64 ft = MsToFileTime(cached.mtime_ms);
    DirInfo->FileInfo.FileAttributes = cached.is_dir ? FILE_ATTRIBUTE_DIRECTORY
                                                     : FILE_ATTRIBUTE_NORMAL;
    DirInfo->FileInfo.FileSize       = cached.is_dir ? 0 : cached.size;
    DirInfo->FileInfo.AllocationSize =
        (DirInfo->FileInfo.FileSize + 4095) & ~uint64_t(4095);
    DirInfo->FileInfo.CreationTime   = ft;
    DirInfo->FileInfo.LastWriteTime  = ft;
    DirInfo->FileInfo.LastAccessTime = ft;
    DirInfo->FileInfo.ChangeTime     = ft;
    std::memcpy(DirInfo->FileNameBuf, wname.c_str(), wname.size() * sizeof(wchar_t));
    return STATUS_SUCCESS;
}

NTSTATUS VirtualDrive::GetFileInfo(FSP_FILE_SYSTEM* /*fs*/,
                                    PVOID FileContext,
                                    FSP_FSCTL_FILE_INFO* FileInfo)
{
    FillFileInfo(*static_cast<FileNode*>(FileContext), FileInfo);
    return STATUS_SUCCESS;
}

// ── Update ────────────────────────────────────────────────────────────────────

NTSTATUS VirtualDrive::Write(FSP_FILE_SYSTEM* fs,
                              PVOID FileContext,
                              PVOID Buffer,
                              UINT64 Offset,
                              ULONG Length,
                              BOOLEAN WriteToEndOfFile,
                              BOOLEAN ConstrainedIo,
                              PULONG PBytesTransferred,
                              FSP_FSCTL_FILE_INFO* FileInfo)
{
    auto* node = static_cast<FileNode*>(FileContext);
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    // Open the write session on the first Write call for this file handle.
    if (!node->write_open) {
        json req = {{"op", "write_open"}, {"path", node->path}};
        protocol::Message resp = self->SendReq(req.dump(), {}, PIPE_WRITE_TIMEOUT);
        json j;
        if (!TryParse(resp.json, j))
            return STATUS_IO_DEVICE_ERROR;
        if (!j.value("ok", false))
            return ErrorToStatus(j.value("error", ""));
        node->write_open = true;
    }

    // Send the chunk with its offset so the Python service can seek the temp
    // buffer correctly for non-sequential writes.
    std::string payload(static_cast<const char*>(Buffer), Length);
    json req = {
        {"op",     "write"},
        {"path",   node->path},
        {"offset", WriteToEndOfFile ? node->size : Offset}
    };
    protocol::Message resp = self->SendReq(req.dump(), payload, PIPE_WRITE_TIMEOUT);
    json j;
    if (!TryParse(resp.json, j))
        return STATUS_IO_DEVICE_ERROR;
    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    *PBytesTransferred = Length;
    if (WriteToEndOfFile)
        node->size += Length;
    else
        node->size = std::max(node->size, Offset + Length);
    FillFileInfo(*node, FileInfo);
    return STATUS_SUCCESS;
}

NTSTATUS VirtualDrive::Flush(FSP_FILE_SYSTEM* /*fs*/,
                              PVOID /*FileContext*/,
                              FSP_FSCTL_FILE_INFO* FileInfo)
{
    // Nothing to flush — data is streamed directly to Android.
    return STATUS_SUCCESS;
}

NTSTATUS VirtualDrive::SetBasicInfo(FSP_FILE_SYSTEM* /*fs*/,
                                     PVOID FileContext,
                                     UINT32 FileAttributes,
                                     UINT64 CreationTime,
                                     UINT64 LastAccessTime,
                                     UINT64 LastWriteTime,
                                     UINT64 ChangeTime,
                                     FSP_FSCTL_FILE_INFO* FileInfo)
{
    // Phone timestamps are not settable — silently succeed so Explorer doesn't error.
    FillFileInfo(*static_cast<FileNode*>(FileContext), FileInfo);
    return STATUS_SUCCESS;
}

NTSTATUS VirtualDrive::SetFileSize(FSP_FILE_SYSTEM* fs,
                                    PVOID FileContext,
                                    UINT64 NewSize,
                                    BOOLEAN SetAllocationSize,
                                    FSP_FSCTL_FILE_INFO* FileInfo)
{
    if (SetAllocationSize) {
        // WinFsp sends SetAllocationSize before actual write — just update the
        // cached size hint so FillFileInfo reports the right allocation.
        auto* node = static_cast<FileNode*>(FileContext);
        node->size = NewSize;
        FillFileInfo(*node, FileInfo);
        return STATUS_SUCCESS;
    }

    auto* node = static_cast<FileNode*>(FileContext);
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    json req = {{"op", "truncate"}, {"path", node->path}, {"new_size", NewSize}};
    protocol::Message resp = self->SendReq(req.dump());
    json j;
    if (!TryParse(resp.json, j))
        return STATUS_IO_DEVICE_ERROR;
    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    node->size = NewSize;
    FillFileInfo(*node, FileInfo);
    return STATUS_SUCCESS;
}

NTSTATUS VirtualDrive::Rename(FSP_FILE_SYSTEM* fs,
                               PVOID FileContext,
                               PWSTR FileName,
                               PWSTR NewFileName,
                               BOOLEAN ReplaceIfExists)
{
    auto* node = static_cast<FileNode*>(FileContext);
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    std::string to = WcharToUtf8(NewFileName);
    NormalizeVPath(to);

    json req = {{"op", "rename"}, {"from", node->path}, {"to", to}};
    protocol::Message resp = self->SendReq(req.dump());
    json j;
    if (!TryParse(resp.json, j))
        return STATUS_IO_DEVICE_ERROR;
    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    // Evict both old and new paths (and their parents) from the C++ cache.
    self->InvalidateStat(node->path);
    self->InvalidateStat(to);
    node->path = to;
    return STATUS_SUCCESS;
}

// ── Delete ────────────────────────────────────────────────────────────────────

NTSTATUS VirtualDrive::CanDelete(FSP_FILE_SYSTEM* fs,
                                  PVOID FileContext,
                                  PWSTR FileName)
{
    auto* node = static_cast<FileNode*>(FileContext);
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    // The node was stat'd during Open, so it is almost certainly still in the
    // C++ cache.  Only fall back to a round-trip on a cache miss (rare).
    StatEntry cached{};
    if (self->LookupStat(node->path, cached))
        return STATUS_SUCCESS;

    json req = {{"op", "stat"}, {"path", node->path}};
    protocol::Message resp = self->SendReq(req.dump());
    json j;
    if (!TryParse(resp.json, j))
        return STATUS_IO_DEVICE_ERROR;
    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", "not_found"));
    return STATUS_SUCCESS;
}

VOID VirtualDrive::Cleanup(FSP_FILE_SYSTEM* fs,
                            PVOID FileContext,
                            PWSTR FileName,
                            ULONG Flags)
{
    auto* node = static_cast<FileNode*>(FileContext);
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);

    // Close any open write session first.
    if (node->write_open) {
        json req = {{"op", "write_close"}, {"path", node->path}};
        self->SendReq(req.dump(), {}, PIPE_WRITE_TIMEOUT);
        node->write_open = false;
        // File contents changed; cached size/mtime are now stale.
        self->InvalidateStat(node->path);
    }

    // Delete if Explorer flagged this handle for deletion.
    if (Flags & FspCleanupDelete) {
        json req = {{"op", "delete"}, {"path", node->path}};
        self->SendReq(req.dump());
        // File is gone; evict its cache entry and parent's listing stat.
        self->InvalidateStat(node->path);
    }
}

VOID VirtualDrive::Close(FSP_FILE_SYSTEM* fs, PVOID FileContext)
{
    auto* node = static_cast<FileNode*>(FileContext);
    auto* self = static_cast<VirtualDrive*>(fs->UserContext);
    // Join all in-flight prefetch tasks first: each captures `node`, so they must
    // finish before the node is freed (otherwise use-after-free). WinFsp
    // guarantees no Read is in flight on this handle once Close is called, so the
    // prefetch futures are the only outstanding work touching the node. Not under
    // readMtx — the tasks acquire it themselves.
    for (auto& slot : node->prefetch)
        if (slot.fut.valid()) slot.fut.wait();
    // Close the persistent read session so SyncDose tears down the TauSync channel
    // and Android releases its open file handle — and free the session slot so
    // another handle can take it.
    if (!node->readSession.empty()) {
        json req = {{"op", "read_close"}, {"session", node->readSession}};
        self->SendReq(req.dump(), {}, VirtualDrive::PIPE_META_TIMEOUT);
        node->readSession.clear();
        self->_readSessionCount.fetch_sub(1, std::memory_order_relaxed);
    }
    // Free the WinFsp directory buffer. No-op for files and for directories that
    // were never enumerated; this is the ONLY place it is deleted, so a partial
    // fill is safely retried via the Reset path instead of racing a reader.
    FspFileSystemDeleteDirectoryBuffer(&node->dirBuffer);
    delete node;
}

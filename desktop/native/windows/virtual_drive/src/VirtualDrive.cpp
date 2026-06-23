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

// Maximum read-ahead window for streaming media (video). Combined with
// prefetch-ahead this keeps a decoder fed: while the player drains the current
// window we fetch the next one in the background, so a sequential read never
// blocks on the round-trip at a window boundary. Memory: up to 2 windows
// (current + next) per open video handle = 200 MB, bounded by the number of
// concurrently open videos (usually 1–2). NOTE: a single 100 MB fetch can take
// minutes over slow Wi-Fi — the read timeouts (PIPE_READ_TIMEOUT here, and the
// Python _READ_TOTAL_TIMEOUT_S) are sized to span a full-window transfer.
static constexpr uint64_t READ_PREFETCH_BYTES_STREAM = 100ULL * 1024 * 1024;

// ── Sequential read-ahead ramp ─────────────────────────────────────────────
// The window is NOT fixed: it starts small and doubles only while reads stay
// sequential. This distinguishes a hover/thumbnail read (a short, often
// non-sequential burst near the start — stays at the small window, fetching
// little) from a real playback/copy (sustained sequential reads — ramps up to
// the max window for throughput). WinFsp gives no reliable open-time "intent"
// signal, so the read *pattern* is the signal.
static constexpr uint64_t READ_WINDOW_MIN  = 256ULL * 1024;  // initial / hover window
static constexpr uint32_t READ_RAMP_MAX    = 9;  // 256 KB << 9 = 128 MB, clamped to the max window
static constexpr uint32_t PREFETCH_RAMP_MIN = 3; // ramp (window ≥ 2 MB) before prefetch

// Max read-ahead window for a node, by its streaming flag.
static uint64_t MaxWindowFor(const FileNode* node)
{
    return node->streaming ? READ_PREFETCH_BYTES_STREAM : READ_PREFETCH_BYTES;
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

void VirtualDrive::PrefetchInto(FileNode* node, uint64_t start, uint64_t len)
{
    protocol::Message resp;
    bool ok = false;
    try {
        json req = {
            {"op", "read"}, {"path", node->path},
            {"offset", start}, {"length", len}
        };
        resp = SendReq(req.dump(), {}, PIPE_READ_TIMEOUT);
        ok = json::parse(resp.json).value("ok", false);
    } catch (...) {
        ok = false;  // prefetch is best-effort; the foreground read will retry
    }

    std::lock_guard<std::mutex> lk(node->readMtx);
    if (ok) {
        auto nc = std::make_unique<FileNode::ReadCache>();
        nc->startOffset = start;
        nc->data.assign(resp.payload.begin(), resp.payload.end());
        // Advance the sequential frontier so a later sync miss past the
        // prefetched region is still seen as sequential (keeps the ramp at max).
        node->lastFetchEnd = std::max(node->lastFetchEnd, start + nc->data.size());
        node->nextCache = std::move(nc);
    }
    node->prefetchInFlight = false;
}

void VirtualDrive::StartPrefetchLocked(FileNode* node, uint64_t offset)
{
    if (!node->streaming || !node->readCache) return;
    // Only prefetch once the handle has proven a sustained sequential read — a
    // hover/thumbnail (low rampStep) must never spawn a 32 MB prefetch.
    if (node->rampStep < PREFETCH_RAMP_MIN) return;
    const auto& rc = *node->readCache;
    uint64_t winEnd = rc.startOffset + static_cast<uint64_t>(rc.data.size());
    uint64_t half   = rc.startOffset + rc.data.size() / 2;
    if (offset < half)        return;  // not yet far enough to prefetch
    if (winEnd >= node->size) return;  // nothing beyond the current window
    if (node->prefetchInFlight) return;                                   // busy
    if (node->nextCache && node->nextCache->startOffset == winEnd) return; // ready

    // Prefetch a full max-size window (the ramp has already engaged).
    uint64_t start = winEnd;
    uint64_t len   = std::min(MaxWindowFor(node), node->size - start);
    node->prefetchInFlight = true;
    node->prefetchStart    = start;
    // Reassigning prefetchFut is safe: a prior task is only ever finished here
    // (prefetchInFlight is set false at its end under readMtx), so the future's
    // destructor does not block. The future is joined in Close before delete.
    try {
        node->prefetchFut = std::async(
            std::launch::async,
            [this, node, start, len]() { PrefetchInto(node, start, len); });
    } catch (...) {
        // Thread/resource exhaustion: skip prefetch this round (the foreground
        // read still works). Never let this escape into the WinFsp callback.
        node->prefetchInFlight = false;
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
        self->StartPrefetchLocked(node, Offset);
        return STATUS_SUCCESS;
    }

    // ── Prefetched next window hit: promote it to current and serve ─────────
    if (node->nextCache && CacheCovers(*node->nextCache, Offset, actual)) {
        node->readCache = std::move(node->nextCache);
        size_t idx = static_cast<size_t>(Offset - node->readCache->startOffset);
        std::memcpy(Buffer, node->readCache->data.data() + idx, actual);
        *PBytesTransferred = actual;
        // Consuming a full prefetched window is a confirmed sequential run; keep
        // the ramp pinned high so any later sync-miss fallback uses the max
        // window immediately instead of re-ramping from small.
        node->rampStep = std::min(node->rampStep + 1, READ_RAMP_MAX);
        self->StartPrefetchLocked(node, Offset);
        return STATUS_SUCCESS;
    }

    // ── Miss: fetch synchronously ──────────────────────────────────────────
    // Adaptive window: grow only while reads stay sequential. A miss that
    // continues exactly where the last fetch ended is a sustained sequential
    // read (playback/copy) → ramp the window up; anything else (first read of a
    // handle, or a seek — e.g. a thumbnailer probing the start/moov atom) resets
    // the ramp, so a hover fetches just READ_WINDOW_MIN instead of the full max.
    bool sequential = (node->lastFetchEnd != 0 && Offset == node->lastFetchEnd);
    node->rampStep = sequential ? std::min(node->rampStep + 1, READ_RAMP_MAX) : 0;
    uint64_t window = std::min(READ_WINDOW_MIN << node->rampStep, MaxWindowFor(node));

    // Release readMtx during the blocking pipe round-trip so a concurrent Read
    // (or the prefetch task) is not stalled behind it. Clamp to EOF.
    uint64_t fetchLen = std::min(
        std::max(static_cast<uint64_t>(actual), window),
        node->size - Offset);
    lk.unlock();

    json req = {
        {"op",     "read"},
        {"path",   node->path},
        {"offset", Offset},
        {"length", fetchLen}
    };
    protocol::Message resp = self->SendReq(req.dump(), {},
                                           VirtualDrive::PIPE_READ_TIMEOUT);
    json j;
    if (!TryParse(resp.json, j))
        return STATUS_IO_DEVICE_ERROR;
    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    ULONG received = static_cast<ULONG>(
        std::min(static_cast<uint64_t>(resp.payload.size()),
                 static_cast<uint64_t>(actual)));
    std::memcpy(Buffer, resp.payload.data(), received);
    *PBytesTransferred = received;

    // Install the fetched chunk as the current window and consider prefetching.
    lk.lock();
    auto rc = std::make_unique<FileNode::ReadCache>();
    rc->startOffset = Offset;
    rc->data.assign(resp.payload.begin(), resp.payload.end());
    node->readCache = std::move(rc);
    // Advance the sequential-fetch frontier so the next contiguous miss is seen
    // as sequential and keeps ramping the window.
    node->lastFetchEnd = std::max(node->lastFetchEnd,
                                  Offset + node->readCache->data.size());
    self->StartPrefetchLocked(node, Offset);
    return STATUS_SUCCESS;
}

// Page size for paginated directory listings.  200 entries × ~60 bytes each
// ≈ 12 KB of JSON per round-trip — fast over Wi-Fi and small enough that
// the first page is visible in Explorer before the rest of the directory loads.
static constexpr int LIST_PAGE_SIZE = 200;

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

    // ── Initialise listing cursor on the very first call ──────────────────
    if (!node->listCursor) {
        node->listCursor = std::make_unique<FileNode::ListCursor>();
    }
    FileNode::ListCursor& cur = *node->listCursor;

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

    // ── Fetch the first page on the very first ReadDirectory call ──────────
    if (!cur.initialized) {
        json req = {
            {"op",    "list_page"},
            {"path",  node->path},
            {"after", nullptr},          // null → start from beginning
            {"limit", LIST_PAGE_SIZE}
        };
        protocol::Message resp = self->SendReq(req.dump(), {}, PIPE_LIST_TIMEOUT);
        json j;
        if (!TryParse(resp.json, j))
            return STATUS_IO_DEVICE_ERROR;
        if (!j.value("ok", false))
            return ErrorToStatus(j.value("error", ""));

        cur.buffer    = j["entries"].get<std::vector<json>>();
        cur.bufIdx    = 0;
        cur.hasMore   = j.value("has_more", false);
        cur.nextAfter = j.value("next_after", "");
        cur.initialized = true;

        seedStatCache(cur.buffer);
    }

    // ── Fill the WinFsp buffer from the cursor ─────────────────────────────
    // Marker-based continuation: when WinFsp calls us with a non-empty Marker
    // we must skip entries up to and including the named entry before filling
    // the output buffer.  Because Android's sort order is deterministic (by
    // name), Marker always names an entry we have already served — it will be
    // found somewhere in the already-fetched portion of the cursor.
    std::string markerUtf8 = Marker ? WcharToUtf8(Marker) : "";
    bool pastMarker = markerUtf8.empty();

    for (;;) {
        // Drain the current page buffer first.
        while (cur.bufIdx < cur.buffer.size()) {
            const auto& entry = cur.buffer[cur.bufIdx];
            std::string name  = entry.value("name",     "");
            bool        is_dir= entry.value("is_dir",   false);
            uint64_t    size  = entry.value("size",     uint64_t(0));
            uint64_t    mtime = entry.value("mtime_ms", uint64_t(0));

            if (!pastMarker) {
                if (name == markerUtf8) pastMarker = true;
                cur.bufIdx++;
                continue;
            }

            std::wstring wname = Utf8ToWchar(name);
            UINT64 ft = MsToFileTime(mtime);

            // FSP_FSCTL_DIR_INFO has a flexible array FileName[] at the end.
            size_t nameBytes = (wname.size() + 1) * sizeof(wchar_t);
            size_t totalSize = sizeof(FSP_FSCTL_DIR_INFO) + nameBytes;
            std::vector<uint8_t> buf(totalSize, 0);
            auto* di = reinterpret_cast<FSP_FSCTL_DIR_INFO*>(buf.data());

            di->Size                    = static_cast<UINT16>(totalSize);
            di->FileInfo.FileAttributes = is_dir ? FILE_ATTRIBUTE_DIRECTORY
                                                  : FILE_ATTRIBUTE_NORMAL;
            di->FileInfo.FileSize       = size;
            di->FileInfo.AllocationSize = (size + 4095) & ~uint64_t(4095);
            di->FileInfo.CreationTime   = ft;
            di->FileInfo.LastWriteTime  = ft;
            di->FileInfo.LastAccessTime = ft;
            di->FileInfo.ChangeTime     = ft;
            std::memcpy(di->FileNameBuf, wname.c_str(), wname.size() * sizeof(wchar_t));

            cur.bufIdx++;

            if (!FspFileSystemAddDirInfo(di, Buffer, Length, PBytesTransferred)) {
                // WinFsp output buffer full — undo the increment so we re-emit
                // this entry when WinFsp calls us again with the previous entry
                // name as the new Marker.
                cur.bufIdx--;
                return STATUS_SUCCESS;
            }
        }

        // Current page drained — fetch next page if available.
        if (!cur.hasMore) break;

        json req = {
            {"op",    "list_page"},
            {"path",  node->path},
            {"after", cur.nextAfter.empty() ? json(nullptr) : json(cur.nextAfter)},
            {"limit", LIST_PAGE_SIZE}
        };
        protocol::Message resp = self->SendReq(req.dump(), {}, PIPE_LIST_TIMEOUT);
        json j;
        if (!TryParse(resp.json, j))
            return STATUS_IO_DEVICE_ERROR;
        if (!j.value("ok", false))
            return ErrorToStatus(j.value("error", ""));

        cur.buffer    = j["entries"].get<std::vector<json>>();
        cur.bufIdx    = 0;
        cur.hasMore   = j.value("has_more", false);
        cur.nextAfter = j.value("next_after", "");

        seedStatCache(cur.buffer);

        // If Android returned an empty page (shouldn't happen, but guard it)
        // and claims there's no more data, break to avoid infinite loop.
        if (cur.buffer.empty()) break;
    }

    // Signal end-of-directory.
    FspFileSystemAddDirInfo(nullptr, Buffer, Length, PBytesTransferred);
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

VOID VirtualDrive::Close(FSP_FILE_SYSTEM* /*fs*/, PVOID FileContext)
{
    auto* node = static_cast<FileNode*>(FileContext);
    // Join any in-flight prefetch first: its async task captures `node`, so it
    // must finish before the node is freed (otherwise use-after-free). WinFsp
    // guarantees no Read is in flight on this handle once Close is called, so the
    // prefetch future is the only outstanding work touching the node.
    if (node->prefetchFut.valid())
        node->prefetchFut.wait();
    delete node;
}

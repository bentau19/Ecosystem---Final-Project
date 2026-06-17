#define NOMINMAX
#include <windows.h>
#include <sddl.h>   // ConvertStringSecurityDescriptorToSecurityDescriptorW

// winfsp.h is pulled in transitively by VirtualDrive.h, which also inserts
// the PNTSTATUS typedef that winfsp v2.0 requires.  Including it here before
// VirtualDrive.h would bypass that fix.
#include "VirtualDrive.h"
#include "WinFspUtil.h"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::json;

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
                                         const std::string& payload)
{
    // Check out an idle connection so concurrent dispatcher threads each get
    // their own pipe — no global serialisation. The pool is sized to the
    // dispatcher thread count, so this rarely blocks.
    ClientNamedPipe* pipe = AcquirePipe();
    try {
        protocol::Message resp = protocol::send(*pipe, {json_str, payload});
        ReleasePipe(pipe);
        return resp;
    } catch (...) {
        // Pipe broke — return it (we are tearing down anyway) and wake Mount()
        // so it can stop the dispatcher from its thread. We must NOT call
        // FspFileSystemStopDispatcher here: we may be on a WinFsp dispatcher
        // thread, which would deadlock.
        ReleasePipe(pipe);
        if (_stopEvent) SetEvent(_stopEvent);
        return protocol::Message{R"({"ok":false,"error":"not_connected"})", ""};
    }
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
    if (error == "not_connected") return STATUS_DEVICE_NOT_CONNECTED;
    if (error == "not_dir")       return STATUS_NOT_A_DIRECTORY;
    if (error == "exists")        return STATUS_OBJECT_NAME_COLLISION;
    if (error == "not_empty")     return STATUS_DIRECTORY_NOT_EMPTY;
    if (error == "timeout")       return STATUS_IO_TIMEOUT;
    return STATUS_IO_DEVICE_ERROR;
}

// ── WinFsp interface vtable ───────────────────────────────────────────────────

// static
FSP_FILE_SYSTEM_INTERFACE VirtualDrive::MakeInterface()
{
    FSP_FILE_SYSTEM_INTERFACE iface = {};
    iface.GetVolumeInfo      = GetVolumeInfo;
    iface.GetSecurityByName  = GetSecurityByName;
    iface.Create             = Create;
    iface.Open               = Open;
    iface.Overwrite          = Overwrite;
    iface.Cleanup            = Cleanup;
    iface.Close              = Close;
    iface.Read               = Read;
    iface.Write              = Write;
    iface.Flush              = Flush;
    iface.GetFileInfo        = GetFileInfo;
    iface.SetBasicInfo       = SetBasicInfo;
    iface.SetFileSize        = SetFileSize;
    iface.CanDelete          = CanDelete;
    iface.Rename             = Rename;
    iface.GetSecurity        = GetSecurity;
    iface.SetSecurity        = SetSecurity;
    iface.ReadDirectory      = ReadDirectory;
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

// ── WinFsp callbacks ──────────────────────────────────────────────────────────

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
        json j = json::parse(resp.json);
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
        json j = json::parse(resp.json);
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
    *PFileContext = node;
    FillFileInfo(*node, FileInfo);
    return STATUS_SUCCESS;
}

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
    json j = json::parse(resp.json);

    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    // Evict parent's cached stat (its listing now includes the new entry).
    self->InvalidateStat(path);
    auto* node = new FileNode{path, is_dir, 0, 0, false};
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
    json j = json::parse(resp.json);
    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    // File was truncated; cached size is now stale.
    self->InvalidateStat(node->path);
    node->size = 0;
    FillFileInfo(*node, FileInfo);
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
        self->SendReq(req.dump());
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
    delete static_cast<FileNode*>(FileContext);
}

// Read-ahead window size. When a Read misses the cache we ask Android for
// this many bytes starting at Offset. Android naturally stops at EOF, so
// requesting more than the remaining file size is always safe.
// 4 MB reduces named-pipe round-trips by ~64× for sequential file copies
// (e.g. 64 KB WinFsp chunks × 64 = one round-trip per 4 MB of data).
static constexpr uint64_t READ_PREFETCH_BYTES = 4ULL * 1024 * 1024;

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

    // ── Cache hit path ─────────────────────────────────────────────────────
    // Serve the request entirely from the prefetch buffer when the requested
    // range [Offset, Offset+actual) falls within the cached window.
    if (node->readCache) {
        const auto& rc = *node->readCache;
        uint64_t cacheEnd = rc.startOffset + static_cast<uint64_t>(rc.data.size());
        if (Offset >= rc.startOffset && (Offset + actual) <= cacheEnd) {
            size_t idx = static_cast<size_t>(Offset - rc.startOffset);
            std::memcpy(Buffer, rc.data.data() + idx, actual);
            *PBytesTransferred = actual;
            return STATUS_SUCCESS;
        }
    }

    // ── Cache miss: fetch a prefetch-sized chunk ───────────────────────────
    // Request up to READ_PREFETCH_BYTES starting at Offset so that subsequent
    // sequential reads hit the cache.  Clamped to the remaining file size so
    // we never ask for bytes past EOF.
    uint64_t fetchLen = std::min(
        std::max(static_cast<uint64_t>(actual), READ_PREFETCH_BYTES),
        node->size - Offset);

    json req = {
        {"op",     "read"},
        {"path",   node->path},
        {"offset", Offset},
        {"length", fetchLen}
    };
    protocol::Message resp = self->SendReq(req.dump());
    json j = json::parse(resp.json);

    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    // Store the full prefetched chunk in the per-handle read cache.
    if (!node->readCache)
        node->readCache = std::make_unique<FileNode::ReadCache>();
    node->readCache->startOffset = Offset;
    node->readCache->data.assign(resp.payload.begin(), resp.payload.end());

    // Deliver only the bytes WinFsp asked for this call.
    ULONG received = static_cast<ULONG>(
        std::min(static_cast<uint64_t>(resp.payload.size()),
                 static_cast<uint64_t>(actual)));
    std::memcpy(Buffer, resp.payload.data(), received);
    *PBytesTransferred = received;
    return STATUS_SUCCESS;
}

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
        protocol::Message resp = self->SendReq(req.dump());
        json j = json::parse(resp.json);
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
    protocol::Message resp = self->SendReq(req.dump(), payload);
    json j = json::parse(resp.json);
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

NTSTATUS VirtualDrive::GetFileInfo(FSP_FILE_SYSTEM* /*fs*/,
                                    PVOID FileContext,
                                    FSP_FSCTL_FILE_INFO* FileInfo)
{
    FillFileInfo(*static_cast<FileNode*>(FileContext), FileInfo);
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
    json j = json::parse(resp.json);
    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    node->size = NewSize;
    FillFileInfo(*node, FileInfo);
    return STATUS_SUCCESS;
}

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
    json j = json::parse(resp.json);
    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", "not_found"));
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
    json j = json::parse(resp.json);
    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    // Evict both old and new paths (and their parents) from the C++ cache.
    self->InvalidateStat(node->path);
    self->InvalidateStat(to);
    node->path = to;
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
        protocol::Message resp = self->SendReq(req.dump());
        json j = json::parse(resp.json);
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
        protocol::Message resp = self->SendReq(req.dump());
        json j = json::parse(resp.json);
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

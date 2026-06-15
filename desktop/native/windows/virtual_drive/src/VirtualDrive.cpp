#define NOMINMAX
#include <windows.h>

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

// Reported total and free space — these are display-only.
static constexpr uint64_t TOTAL_SIZE = 1ULL * 1024 * 1024 * 1024 * 1024; // 1 TB
static constexpr uint64_t FREE_SIZE  = 500ULL * 1024 * 1024 * 1024;      // 500 GB

// Sector / cluster geometry expected by WinFsp.
static constexpr uint16_t BYTES_PER_SECTOR    = 512;
static constexpr uint16_t SECTORS_PER_CLUSTER = 8;   // 4 KB clusters

// FspCleanupDelete / FspCleanupSetAllocationSize are enum values in winfsp.h.
// No local redefinitions needed.

// ── Helpers ───────────────────────────────────────────────────────────────────

// Build a minimal security descriptor that grants Everyone full access.
// WinFsp requires GetSecurityByName to return *something* — we return this
// placeholder so Explorer can open any path without an access-denied error.
static PSECURITY_DESCRIPTOR MakeEveryoneFullSD()
{
    static SECURITY_DESCRIPTOR sd = {};
    static bool initialised = false;
    if (!initialised) {
        InitializeSecurityDescriptor(&sd, SECURITY_DESCRIPTOR_REVISION);
        SetSecurityDescriptorDacl(&sd, TRUE, nullptr, FALSE);
        initialised = true;
    }
    return &sd;
}

// ── VirtualDrive implementation ───────────────────────────────────────────────

VirtualDrive::VirtualDrive(ClientNamedPipe& pipe) : _pipe(pipe) {}

VirtualDrive::~VirtualDrive()
{
    // Mount() calls FspFileSystemStopDispatcher before returning, so by the
    // time the destructor runs the dispatcher is already stopped.
    if (_fs) {
        FspFileSystemDelete(_fs);
        _fs = nullptr;
    }
}

protocol::Message VirtualDrive::SendReq(const std::string& json_str,
                                         const std::string& payload)
{
    std::lock_guard<std::mutex> lk(_pipeMtx);
    try {
        return protocol::send(_pipe, {json_str, payload});
    } catch (...) {
        // Pipe broke — wake Mount() so it can stop the dispatcher from its thread.
        // We must NOT call FspFileSystemStopDispatcher here because we may be
        // running on a WinFsp dispatcher thread, which would deadlock.
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
    params.FileInfoTimeout         = 1000;        // ms — keep stat cache short
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

    st = FspFileSystemStartDispatcher(_fs, 0);
    if (!NT_SUCCESS(st)) {
        FspFileSystemDelete(_fs);
        _fs = nullptr;
        throw std::runtime_error("FspFileSystemStartDispatcher failed: " + std::to_string(st));
    }

    // Block until SendReq detects a pipe break and signals _stopEvent.
    // FspFileSystemWaitDispatcher was removed in WinFsp v2.0; we use a manual
    // event instead.  StopDispatcher must be called from this thread (not a
    // WinFsp callback thread) to avoid deadlock.
    _stopEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    WaitForSingleObject(_stopEvent, INFINITE);
    CloseHandle(_stopEvent);
    _stopEvent = nullptr;

    FspFileSystemStopDispatcher(_fs);
}

// ── WinFsp callbacks ──────────────────────────────────────────────────────────

NTSTATUS VirtualDrive::GetVolumeInfo(FSP_FILE_SYSTEM* fs,
                                      FSP_FSCTL_VOLUME_INFO* vi)
{
    std::memset(vi, 0, sizeof(*vi));
    vi->TotalSize  = TOTAL_SIZE;
    vi->FreeSize   = FREE_SIZE;
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

    // stat the path to know if it exists and whether it's a directory.
    json req = {{"op", "stat"}, {"path", path}};
    protocol::Message resp = self->SendReq(req.dump());
    json j = json::parse(resp.json);

    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", "not_found"));

    if (PFileAttributes)
        *PFileAttributes = j.value("is_dir", false)
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

    json req = {{"op", "stat"}, {"path", path}};
    protocol::Message resp = self->SendReq(req.dump());
    json j = json::parse(resp.json);

    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", "not_found"));

    auto* node = new FileNode{
        path,
        j.value("is_dir",   false),
        j.value("size",     uint64_t(0)),
        j.value("mtime_ms", uint64_t(0)),
        false
    };
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
    }

    // Delete if Explorer flagged this handle for deletion.
    if (Flags & FspCleanupDelete) {
        json req = {{"op", "delete"}, {"path", node->path}};
        self->SendReq(req.dump());
    }
}

VOID VirtualDrive::Close(FSP_FILE_SYSTEM* /*fs*/, PVOID FileContext)
{
    delete static_cast<FileNode*>(FileContext);
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

    json req = {
        {"op",     "read"},
        {"path",   node->path},
        {"offset", Offset},
        {"length", actual}
    };
    protocol::Message resp = self->SendReq(req.dump());
    json j = json::parse(resp.json);

    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    ULONG received = static_cast<ULONG>(resp.payload.size());
    if (received > actual) received = actual;
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

    // Verify the path still exists; let the server decide if it can be deleted.
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

    json req = {{"op", "list"}, {"path", node->path}};
    protocol::Message resp = self->SendReq(req.dump());
    json j = json::parse(resp.json);

    if (!j.value("ok", false))
        return ErrorToStatus(j.value("error", ""));

    // Track whether we have passed the Marker entry (for partial reads).
    std::string markerUtf8 = Marker ? WcharToUtf8(Marker) : "";
    bool pastMarker = markerUtf8.empty();

    for (const auto& entry : j["entries"]) {
        std::string name    = entry.value("name",     "");
        bool        is_dir  = entry.value("is_dir",   false);
        uint64_t    size    = entry.value("size",     uint64_t(0));
        uint64_t    mtime   = entry.value("mtime_ms", uint64_t(0));

        if (!pastMarker) {
            if (name == markerUtf8) pastMarker = true;
            continue;
        }

        std::wstring wname = Utf8ToWchar(name);
        UINT64 ft = MsToFileTime(mtime);

        // Allocate the dir-info struct on the stack.
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

        if (!FspFileSystemAddDirInfo(di, Buffer, Length, PBytesTransferred))
            return STATUS_SUCCESS; // buffer full — WinFsp will call again with Marker
    }

    // Signal end-of-directory.
    FspFileSystemAddDirInfo(nullptr, Buffer, Length, PBytesTransferred);
    return STATUS_SUCCESS;
}

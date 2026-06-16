#pragma once
#define NOMINMAX
#include <windows.h>

// <windows.h> alone does not define NTSTATUS; it comes from <winternl.h>
// (which <winfsp/winfsp.h> includes below). We need it here, before winfsp.h,
// to declare PNTSTATUS — which the WinFsp v2.0 directory-buffer API uses but
// winternl.h itself does not provide. Including winternl.h now defines NTSTATUS;
// its later inclusion via winfsp.h is a guarded no-op.
#include <winternl.h>
#ifndef PNTSTATUS
typedef NTSTATUS* PNTSTATUS;
#endif

#include <winfsp/winfsp.h>

#include <condition_variable>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <vector>

#include "ClientNamedPipe.h"
#include "Protocol.h"

// Per-open-handle context allocated in Open/Create and freed in Close.
struct FileNode {
    std::string path;       // UTF-8 virtual path, e.g. "/DCIM/photo.jpg"
    bool        is_dir;
    uint64_t    size;
    uint64_t    mtime_ms;   // Unix epoch milliseconds; 0 = unknown
    bool        write_open; // true between write_open and write_close pipe ops
};

class VirtualDrive {
public:
    // Takes ownership of a pool of pipe connections; all must remain valid for
    // the lifetime of this object. Concurrency = pool size: each WinFsp
    // dispatcher thread checks out one idle connection per request.
    explicit VirtualDrive(std::vector<std::unique_ptr<ClientNamedPipe>> pipes);
    ~VirtualDrive();

    // Mount the filesystem at mountPoint (e.g. L"E:") and block until the
    // WinFsp dispatcher stops or a pipe breaks.
    void Mount(const std::wstring& mountPoint);

private:
    // Connection pool. _pipes owns the connections; _idle is the free-list of
    // those not currently checked out by a request. Each ClientNamedPipe owns
    // its own I/O event, so distinct connections are safe to use concurrently;
    // the pool only ensures one connection is never used by two threads at once.
    std::vector<std::unique_ptr<ClientNamedPipe>> _pipes;
    std::queue<ClientNamedPipe*> _idle;
    std::mutex                   _poolMtx;
    std::condition_variable      _poolCv;

    FSP_FILE_SYSTEM* _fs = nullptr;
    HANDLE           _stopEvent = nullptr; // signalled by SendReq on pipe failure

    // Thread-safe single round-trip to the Python server. Checks out an idle
    // pooled connection, sends the request, reads the response, returns the
    // connection. Blocks only if every connection is busy.
    protocol::Message SendReq(const std::string& json,
                              const std::string& payload = {});

    // Pool check-out / return.
    ClientNamedPipe* AcquirePipe();
    void             ReleasePipe(ClientNamedPipe* pipe);

    // Helper: populate a FSP_FSCTL_FILE_INFO from a FileNode.
    static void FillFileInfo(const FileNode& node, FSP_FSCTL_FILE_INFO* fi);

    // Helper: convert a JSON "error" string to an NTSTATUS code.
    static NTSTATUS ErrorToStatus(const std::string& error);

    // Build the WinFsp interface vtable.
    static FSP_FILE_SYSTEM_INTERFACE MakeInterface();

    // ── WinFsp static callbacks ───────────────────────────────────────────────
    // All cast fs->UserContext to VirtualDrive* and delegate to instance logic.

    static NTSTATUS GetVolumeInfo(
        FSP_FILE_SYSTEM* fs,
        FSP_FSCTL_VOLUME_INFO* vi);

    static NTSTATUS GetSecurityByName(
        FSP_FILE_SYSTEM* fs,
        PWSTR FileName,
        PUINT32 PFileAttributes,
        PSECURITY_DESCRIPTOR SecurityDescriptor,
        SIZE_T* PSecurityDescriptorSize);

    static NTSTATUS Create(
        FSP_FILE_SYSTEM* fs,
        PWSTR FileName,
        UINT32 CreateOptions,
        UINT32 GrantedAccess,
        UINT32 FileAttributes,
        PSECURITY_DESCRIPTOR SecurityDescriptor,
        UINT64 AllocationSize,
        PVOID* PFileContext,
        FSP_FSCTL_FILE_INFO* FileInfo);

    static NTSTATUS Open(
        FSP_FILE_SYSTEM* fs,
        PWSTR FileName,
        UINT32 CreateOptions,
        UINT32 GrantedAccess,
        PVOID* PFileContext,
        FSP_FSCTL_FILE_INFO* FileInfo);

    static NTSTATUS Overwrite(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        UINT32 FileAttributes,
        BOOLEAN ReplaceFileAttributes,
        UINT64 AllocationSize,
        FSP_FSCTL_FILE_INFO* FileInfo);

    static VOID Cleanup(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PWSTR FileName,
        ULONG Flags);

    static VOID Close(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext);

    static NTSTATUS Read(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PVOID Buffer,
        UINT64 Offset,
        ULONG Length,
        PULONG PBytesTransferred);

    static NTSTATUS Write(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PVOID Buffer,
        UINT64 Offset,
        ULONG Length,
        BOOLEAN WriteToEndOfFile,
        BOOLEAN ConstrainedIo,
        PULONG PBytesTransferred,
        FSP_FSCTL_FILE_INFO* FileInfo);

    static NTSTATUS Flush(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        FSP_FSCTL_FILE_INFO* FileInfo);

    static NTSTATUS GetFileInfo(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        FSP_FSCTL_FILE_INFO* FileInfo);

    static NTSTATUS SetBasicInfo(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        UINT32 FileAttributes,
        UINT64 CreationTime,
        UINT64 LastAccessTime,
        UINT64 LastWriteTime,
        UINT64 ChangeTime,
        FSP_FSCTL_FILE_INFO* FileInfo);

    static NTSTATUS SetFileSize(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        UINT64 NewSize,
        BOOLEAN SetAllocationSize,
        FSP_FSCTL_FILE_INFO* FileInfo);

    static NTSTATUS CanDelete(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PWSTR FileName);

    static NTSTATUS Rename(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PWSTR FileName,
        PWSTR NewFileName,
        BOOLEAN ReplaceIfExists);

    static NTSTATUS GetSecurity(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PSECURITY_DESCRIPTOR SecurityDescriptor,
        SIZE_T* PSecurityDescriptorSize);

    static NTSTATUS SetSecurity(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        SECURITY_INFORMATION SecurityInformation,
        PSECURITY_DESCRIPTOR ModificationDescriptor);

    static NTSTATUS ReadDirectory(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PWSTR Pattern,
        PWSTR Marker,
        PVOID Buffer,
        ULONG Length,
        PULONG PBytesTransferred);
};

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
#include <future>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <chrono>
#include <optional>
#include <unordered_map>
#include <vector>

#include <nlohmann/json.hpp>

#include "ClientNamedPipe.h"
#include "Protocol.h"

// Per-open-handle context allocated in Open/Create and freed in Close.
struct FileNode {
    std::string path;       // UTF-8 virtual path, e.g. "/DCIM/photo.jpg"
    bool        is_dir;
    uint64_t    size;
    uint64_t    mtime_ms;   // Unix epoch milliseconds; 0 = unknown
    bool        write_open; // true between write_open and write_close pipe ops

    // ── Directory listing (directories only) ──────────────────────────────
    //
    // Strategy: fetch entries lazily in pages of LIST_PAGE_SIZE via the
    // "list_page" op.  The first page is fetched on the first ReadDirectory
    // call (Marker == null); subsequent pages are fetched on demand as the
    // buffered entries are consumed.  All Marker-continuation calls on this
    // handle are served from the in-memory buffer with zero pipe overhead
    // until the buffer is drained and another page is needed.
    //
    // ListCursor tracks pagination state for one open directory handle.
    struct ListCursor {
        std::vector<nlohmann::json> buffer;    // fetched but not yet given to WinFsp
        size_t      bufIdx     = 0;            // next unconsumed index in buffer
        bool        hasMore    = true;         // false once Android says last page
        std::string nextAfter;                 // cursor: last name of previous page
        bool        initialized = false;       // true after the first page fetch
    };
    std::unique_ptr<ListCursor> listCursor;    // null for files

    // ── Sequential read-ahead cache (files only) ───────────────────────────
    // When a Read is issued we fetch a larger prefetch window from Android and
    // store the surplus here.  Sequential reads that fall inside the window
    // (common for file copies) are served without any named-pipe round-trip.
    struct ReadCache {
        std::vector<uint8_t> data;
        uint64_t             startOffset = 0; // byte offset of data[0] in the file
    };

    // true for media files (set in Open by extension). Streaming handles get a
    // larger window and asynchronous prefetch-ahead so playback never stalls on
    // the round-trip at a window boundary.
    bool streaming = false;

    // ── Read-cache state (guarded by readMtx) ──────────────────────────────
    // readMtx guards readCache, nextCache and the prefetch/ramp bookkeeping
    // below. WinFsp may dispatch concurrent Reads on one handle, and a background
    // prefetch task mutates these too, so all access is serialised.
    std::mutex                 readMtx;
    std::unique_ptr<ReadCache> readCache;   // current window serving reads
    std::unique_ptr<ReadCache> nextCache;   // prefetched next window (ready)
    bool                       prefetchInFlight = false; // a prefetch task is running
    uint64_t                   prefetchStart    = 0;     // offset that task is fetching
    std::future<void>          prefetchFut;              // joined in Close before delete

    // ── Sequential read-ahead ramp ─────────────────────────────────────────
    // The fetch window starts small (so a hover/thumbnail read fetches little)
    // and grows only while reads continue sequentially (a real playback/copy),
    // so "real" reads get large chunks while previews stay cheap.
    uint64_t lastFetchEnd = 0;   // end offset of the furthest window fetched so far
    uint32_t rampStep     = 0;   // consecutive-sequential-miss counter (drives window)
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

    // ── C++ metadata caches ───────────────────────────────────────────────────
    // Caching at this layer eliminates the named-pipe round-trip to Python for
    // stat hits that Python itself would serve from its own short-TTL cache.
    // Mutations (Create, Cleanup-write, Delete, Rename, Overwrite) always call
    // InvalidateStat so stale data is bounded.

    struct StatEntry {
        bool     is_dir;
        uint64_t size;
        uint64_t mtime_ms;
        std::chrono::steady_clock::time_point expiry;
    };

    struct CachedVolume {
        uint64_t total;
        uint64_t free;
        std::chrono::steady_clock::time_point expiry;
    };

    // TTLs in seconds — match the Python-side _CACHE_TTL_SECONDS (30 s).
    static constexpr int STAT_CACHE_TTL_S   = 30;
    static constexpr int VOLUME_CACHE_TTL_S = 60;

    std::unordered_map<std::string, StatEntry> _statCache;
    std::mutex                                  _statMtx;
    std::optional<CachedVolume>                 _volumeCache;
    std::mutex                                  _volumeMtx;

    void CacheStat(const std::string& path, const StatEntry& e);
    bool LookupStat(const std::string& path, StatEntry& out);
    void InvalidateStat(const std::string& path);

    // Per-op pipe timeouts, sized to each op's legitimate duration so a slow
    // phone frees the WinFsp dispatcher thread fast (instead of hanging Explorer
    // for the whole wait), while genuinely long ops still complete. The C++
    // readFrame on the pipe blocks for the whole Python round-trip (Python answers
    // only after the phone does), so each constant must exceed its op's worst case:
    //   META  : near-instant metadata (stat/create/delete/rename/truncate/volume/
    //           write_close). This is a *backstop* only: the Python side now bounds
    //           each metadata op itself (connect + stall ≈ 6 s worst case) and always
    //           returns a framed response first, so this must sit comfortably ABOVE
    //           that to avoid a timeout race that frame-desyncs the pipe and churns
    //           ReplacePipe. On timeout SendReq swaps the pipe and returns a retryable
    //           STATUS_IO_TIMEOUT; the drive stays mounted.
    //   LIST  : a cold large-folder enumeration the Python side caps at
    //           _LIST_FULL_TIMEOUT_S = 60 s — must sit above that.
    //   READ  : may stream a full 100 MB window; set above the Python read cap
    //           (_READ_TOTAL_TIMEOUT_S = 300 s) so it is only a backstop for a
    //           wedged SyncDose, not a merely slow phone.
    //   WRITE : a single chunk delivered to the phone over slow Wi-Fi — minutes
    //           are legitimate, so it gets the same generous budget as reads.
    static constexpr std::chrono::milliseconds PIPE_META_TIMEOUT{10'000};
    static constexpr std::chrono::milliseconds PIPE_LIST_TIMEOUT{90'000};
    static constexpr std::chrono::milliseconds PIPE_READ_TIMEOUT{330'000};
    static constexpr std::chrono::milliseconds PIPE_WRITE_TIMEOUT{330'000};

    // Reconnect policy for replacing a poisoned (timed-out / broken) pipe slot.
    // Kept here so they are visible alongside the other per-op tuning constants.
    static constexpr int   RECONNECT_ATTEMPTS    = 5;
    static constexpr DWORD RECONNECT_BACKOFF_MS  = 200;

    // Thread-safe single round-trip to the Python server. Checks out an idle
    // pooled connection, sends the request, reads the response, returns the
    // connection. Blocks only if every connection is busy. On a pipe timeout the
    // connection is byte-stream-desynced and is replaced (ReplacePipe) rather
    // than reused, and the op returns a retryable {"ok":false,"error":"timeout"}.
    protocol::Message SendReq(const std::string& json,
                              const std::string& payload = {},
                              std::chrono::milliseconds timeout = PIPE_META_TIMEOUT);

    // Pool check-out / return / replace-poisoned.
    ClientNamedPipe* AcquirePipe();
    void             ReleasePipe(ClientNamedPipe* pipe);
    void             ReplacePipe(ClientNamedPipe* poisoned);

    // Background prefetch of [start, start+len) into node->nextCache. Runs on a
    // std::async task whose future is joined in Close before the node is freed.
    void PrefetchInto(FileNode* node, uint64_t start, uint64_t len);

    // If a streaming read has advanced into the back half of the current window
    // and more file remains, launch an async prefetch of the next window. MUST be
    // called with node->readMtx held.
    void StartPrefetchLocked(FileNode* node, uint64_t offset);

    // True if path has a streaming-media extension (video). Such files get a
    // larger read window and prefetch-ahead.
    static bool IsStreamingPath(const std::string& path);

    // Helper: populate a FSP_FSCTL_FILE_INFO from a FileNode.
    static void FillFileInfo(const FileNode& node, FSP_FSCTL_FILE_INFO* fi);

    // Helper: convert a JSON "error" string to an NTSTATUS code.
    static NTSTATUS ErrorToStatus(const std::string& error);

    // Build the WinFsp interface vtable.
    static FSP_FILE_SYSTEM_INTERFACE MakeInterface();

    // ── WinFsp static callbacks ───────────────────────────────────────────────
    // All cast fs->UserContext to VirtualDrive* and delegate to instance logic.
    // Organised by CRUD: Volume/Security → Create → Read → Update → Delete.

    // ── Volume / Security ─────────────────────────────────────────────────────

    static NTSTATUS GetVolumeInfo(
        FSP_FILE_SYSTEM* fs,
        FSP_FSCTL_VOLUME_INFO* vi);

    static NTSTATUS GetSecurityByName(
        FSP_FILE_SYSTEM* fs,
        PWSTR FileName,
        PUINT32 PFileAttributes,
        PSECURITY_DESCRIPTOR SecurityDescriptor,
        SIZE_T* PSecurityDescriptorSize);

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

    // ── Create ────────────────────────────────────────────────────────────────

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

    // ── Read ──────────────────────────────────────────────────────────────────

    static NTSTATUS Read(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PVOID Buffer,
        UINT64 Offset,
        ULONG Length,
        PULONG PBytesTransferred);

    static NTSTATUS ReadDirectory(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PWSTR Pattern,
        PWSTR Marker,
        PVOID Buffer,
        ULONG Length,
        PULONG PBytesTransferred);

    static NTSTATUS GetFileInfo(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        FSP_FSCTL_FILE_INFO* FileInfo);

    // ── Update ────────────────────────────────────────────────────────────────

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

    static NTSTATUS Rename(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PWSTR FileName,
        PWSTR NewFileName,
        BOOLEAN ReplaceIfExists);

    // ── Delete ────────────────────────────────────────────────────────────────

    static NTSTATUS CanDelete(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PWSTR FileName);

    static VOID Cleanup(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PWSTR FileName,
        ULONG Flags);

    static VOID Close(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext);
};

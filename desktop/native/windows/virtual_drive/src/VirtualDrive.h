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

#include <atomic>
#include <condition_variable>
#include <deque>
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
    // WinFsp's own directory buffer. ReadDirectory fills it once per open
    // handle — pulling every "list_page" page in a single call — and WinFsp then
    // serves all Marker-continuation calls out of it with zero pipe traffic.
    //
    // This replaces a hand-rolled page cursor that got the Marker protocol
    // wrong in two ways (it resumed one entry PAST the marker, and it never
    // reset when WinFsp restarted a scan with a null Marker), silently
    // truncating any directory larger than one WinFsp buffer (~450 entries).
    // WinFsp owns the sort, the marker binary search, the fill lock and the
    // end-of-directory marker, so none of that has to be re-derived here.
    // Freed in Close; refilled when Acquire is passed Reset = (Marker == null).
    PVOID dirBuffer = nullptr;

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

    // ── One in-flight background prefetch task ──────────────────────────────
    // Each PrefetchSlot owns the future for one async fetch of the window
    // starting at `start`. `gen` tags the seek generation the task was launched
    // under: a result whose gen no longer matches the node's current generation
    // (the player seeked away) is discarded instead of inserted into `ready`.
    // Slots are pruned once complete and all are joined in Close before the node
    // is freed (the task captures `node`).
    struct PrefetchSlot {
        uint64_t          start = 0;   // file offset the task is fetching
        uint64_t          gen   = 0;   // seek generation at launch
        std::future<void> fut;         // joined / pruned under readMtx
    };

    // ── Read-cache state (guarded by readMtx) ──────────────────────────────
    // readMtx guards readCache, the `ready` pipeline, the in-flight prefetch
    // slots and the ramp/streaming bookkeeping below. WinFsp may dispatch
    // concurrent Reads on one handle, and background prefetch tasks mutate these
    // too, so all access is serialised.
    std::mutex                 readMtx;
    std::unique_ptr<ReadCache> readCache;   // current window serving reads
    // Prefetched windows ahead of the read frontier, kept in ascending
    // startOffset order. Replaces the old single nextCache so a streaming handle
    // keeps PREFETCH_DEPTH windows buffered and never stalls one window at a time.
    std::deque<std::unique_ptr<ReadCache>> ready;
    std::vector<PrefetchSlot>  prefetch;       // in-flight prefetch tasks (joined in Close)
    uint64_t                   prefetchFrontier = 0;  // next offset to prefetch from
    uint64_t                   prefetchGen      = 0;  // bumped on each seek; tags slots

    // ── Streaming read session ──────────────────────────────────────────────
    // Persistent Python read-channel id for this handle (the "read_open" op
    // returns it). Empty until the first streaming miss opens it; reused for
    // every subsequent read/prefetch so the per-fetch TauSync handshake and
    // Android file-open are paid once per handle, not once per window.
    std::string readSession;

    // ── Sequential read-ahead ramp (NON-streaming files only) ───────────────
    // The fetch window starts small (so a hover/thumbnail read fetches little)
    // and grows only while reads continue sequentially (a real file copy), so
    // "real" reads get large chunks while previews stay cheap. Streaming handles
    // bypass the ramp and use a fixed STREAM_WINDOW with the prefetch pipeline.
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

    // ── Persistent read-session policy ────────────────────────────────────────
    // A session keeps one TauSync channel (and one open file on the phone) alive
    // across many reads, so a sustained copy pays the channel handshake once
    // instead of once per window. It is not free: each live session pins one of
    // Android's 12 peer-request handler threads for its whole lifetime (its
    // serve loop blocks until read_close), and when that pool saturates new
    // dispatches are REJECTED and deferred — so metadata ops stall and the drive
    // feels frozen. Cap sessions well below the pool so stat/list/write always
    // have threads; a handle denied a session just falls back to one-shot
    // fetches, which are slower but block nobody.
    static constexpr int      MAX_READ_SESSIONS = 6;
    // Promote a handle to a session only once it has read ~768 KB contiguously
    // (rampStep 2 ⇒ the 3rd sequential window). Lower would open sessions for
    // thumbnailers and hover previews that read a file once and never return.
    static constexpr uint32_t SESSION_RAMP_MIN  = 2;
    std::atomic<int>          _readSessionCount{0};

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

    // Background prefetch of [start, start+len) into node->ready (in ascending
    // offset order). `gen` is the seek generation at launch — if the player
    // seeked away (node->prefetchGen advanced) the result is discarded. Runs on a
    // std::async task whose future lives in a PrefetchSlot and is joined in Close
    // before the node is freed.
    void PrefetchInto(FileNode* node, uint64_t start, uint64_t len, uint64_t gen);

    // Top the prefetch pipeline up to PREFETCH_DEPTH windows ahead of `frontier`
    // for a streaming handle: prune completed prefetch slots, drop ready windows
    // that fell behind a seek, and launch async prefetches for any of the next
    // PREFETCH_DEPTH windows not already ready or in flight. MUST be called with
    // node->readMtx held.
    void RefillPipelineLocked(FileNode* node, uint64_t frontier);

    // True if path has a streaming-media extension (video). Such files get a
    // larger read window and prefetch-ahead.
    static bool IsStreamingPath(const std::string& path);

    // Ensure node->readSession names a live persistent read channel, opening one
    // if needed. Returns true if the handle has a session on return.
    //
    // MUST be called with `lk` (node->readMtx) held; releases and re-acquires it
    // around the pipe round-trip, so callers must re-check any state they cached
    // across the call. Returns false — harmlessly, the caller then does a
    // one-shot fetch — when MAX_READ_SESSIONS are already live or the open
    // fails. Never throws.
    bool EnsureReadSession(FileNode* node, std::unique_lock<std::mutex>& lk);

    // Close node's persistent read session (if any) and free its slot. Safe to
    // call with no session open. MUST be called with `lk` held.
    void DropReadSession(FileNode* node, std::unique_lock<std::mutex>& lk);

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

    // WinFsp calls this INSTEAD of ReadDirectory when a query names a single
    // file (FindFirstFile("E:\dir\one.txt")), which requires
    // PassQueryDirectoryFileName — already set in Mount. Without it such a query
    // enumerates the whole directory; with it, one cached stat answers it.
    static NTSTATUS GetDirInfoByName(
        FSP_FILE_SYSTEM* fs,
        PVOID FileContext,
        PWSTR FileName,
        FSP_FSCTL_DIR_INFO* DirInfo);

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

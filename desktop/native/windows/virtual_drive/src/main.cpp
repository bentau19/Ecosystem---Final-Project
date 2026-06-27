#define NOMINMAX
#include <windows.h>

#include "ClientNamedPipe.h"
#include "DriveLetterUtil.h"
#include "PipeException.h"
#include "VirtualDrive.h"
#include "WinFspUtil.h"

#include <chrono>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

// Pipe name and buffer size come from Protocol.h so they stay in sync with VirtualDrive.cpp.

// Retry parameters for the initial pipe connection. SyncDose now pre-creates all
// PIPE_POOL_SIZE server instances before it launches this exe (see
// VirtualDriveService._prewarm_pipes), so every connect below normally succeeds on
// the first try and the pool fills in well under a millisecond. The short retry
// interval is only a fallback for a brief restart race (e.g. the exe-watchdog
// relaunching this process before the server's acceptors have recycled): keep it
// small so such a race costs ~100 ms, not seconds.
static constexpr int RETRY_INTERVAL_MS = 100;
static constexpr int RETRY_TIMEOUT_MS  = 30000;

// Number of pipe connections to open. Sets the desktop-side concurrency ceiling:
// this many virtual-drive ops can be in flight at once. Must be <= the Python
// server's _MAX_CONNECTIONS. Sized at 12 so a streaming read (1 foreground +
// 1 background prefetch pipe per open video) does not starve metadata ops.
static constexpr int PIPE_POOL_SIZE = 12;

// ── Entry point ───────────────────────────────────────────────────────────────

int wmain(int /*argc*/, wchar_t* /*argv*/[])
{
    // 0. Load winfsp-x64.dll. It is delay-loaded (not on PATH), so this must run
    //    before any Fsp* call; FspLoad locates the DLL via the WinFsp registry
    //    InstallDir. Failure means WinFsp is not installed.
    if (!NT_SUCCESS(FspLoad(nullptr))) {
        std::wcerr << L"[VirtualDrive] WinFsp is not installed. "
                      L"Install it from https://winfsp.dev\n";
        return 1;
    }

    // 1. Global mutex — only one VirtualDrive.exe may run at a time.
    HANDLE hMutex = CreateMutexW(nullptr, FALSE, L"Global\\SyncDoseVDrive");
    if (!hMutex) {
        std::wcerr << L"[VirtualDrive] Failed to create mutex.\n";
        return 1;
    }
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        std::wcerr << L"[VirtualDrive] Another instance is already running.\n";
        CloseHandle(hMutex);
        return 1;
    }

    // 2. Connect to SyncDose's pipe server, opening PIPE_POOL_SIZE connections.
    //    The server pre-creates all PIPE_POOL_SIZE instances up front
    //    (PIPE_UNLIMITED_INSTANCES) and serves them concurrently, so these connects
    //    normally all succeed immediately and the loop completes in microseconds —
    //    the drive then mounts without delay. A connect can still transiently fail
    //    with ERROR_PIPE_BUSY during a restart race (server acceptors mid-recycle),
    //    so each attempt is retried at the short RETRY_INTERVAL_MS.
    std::vector<std::unique_ptr<ClientNamedPipe>> pipes;
    {
        int elapsed = 0;
        while (static_cast<int>(pipes.size()) < PIPE_POOL_SIZE
               && elapsed < RETRY_TIMEOUT_MS) {
            try {
                pipes.push_back(std::make_unique<ClientNamedPipe>(
                    protocol::PIPE_BUFFER_SIZE, protocol::PIPE_BUFFER_SIZE,
                    protocol::PIPE_NAME_A, /*duplex=*/true));
            } catch (const PipeException&) {
                std::wcout << L"[VirtualDrive] Waiting for SyncDose ("
                           << pipes.size() << L"/" << PIPE_POOL_SIZE
                           << L" connections)...\n";
                std::this_thread::sleep_for(
                    std::chrono::milliseconds(RETRY_INTERVAL_MS));
                elapsed += RETRY_INTERVAL_MS;
            }
        }
        if (static_cast<int>(pipes.size()) < PIPE_POOL_SIZE) {
            std::wcerr << L"[VirtualDrive] Could not open " << PIPE_POOL_SIZE
                       << L" connections to SyncDose after "
                       << (RETRY_TIMEOUT_MS / 1000) << L"s. Exiting.\n";
            CloseHandle(hMutex);
            return 1;
        }
    }
    std::wcout << L"[VirtualDrive] Connected to SyncDose ("
               << PIPE_POOL_SIZE << L" connections).\n";

    // 3. Find the first available drive letter.
    std::string mountStr;
    try {
        mountStr = FindFirstAvailableDriveLetter();
    } catch (const std::exception& e) {
        std::wcerr << L"[VirtualDrive] " << e.what() << L"\n";
        CloseHandle(hMutex);
        return 1;
    }
    std::wstring mountPoint = Utf8ToWchar(mountStr);
    std::wcout << L"[VirtualDrive] Mounting at " << mountPoint << L"\n";

    // 4. Mount the virtual filesystem — blocks until unmounted or pipe breaks.
    try {
        VirtualDrive drive(std::move(pipes));
        drive.Mount(mountPoint);
    } catch (const std::exception& e) {
        std::wcerr << L"[VirtualDrive] Fatal: " << e.what() << L"\n";
        CloseHandle(hMutex);
        return 1;
    }

    std::wcout << L"[VirtualDrive] Unmounted cleanly.\n";
    CloseHandle(hMutex);
    return 0;
}

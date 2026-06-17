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

// Pipe name SyncDose.exe exposes for VirtualDrive IPC.
static constexpr char PIPE_NAME[] = "\\\\.\\pipe\\SyncDoseVDrive";

// Retry parameters for the initial pipe connection.
static constexpr int RETRY_INTERVAL_MS = 2000;
static constexpr int RETRY_TIMEOUT_MS  = 30000;

// Number of pipe connections to open. Sets the desktop-side concurrency ceiling:
// this many virtual-drive ops can be in flight at once. Must be <= the Python
// server's _MAX_CONNECTIONS.
static constexpr int PIPE_POOL_SIZE = 8;

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

    // 2. Retry-connect to SyncDose's pipe server, opening PIPE_POOL_SIZE
    //    connections. The server accepts each on its own instance
    //    (PIPE_UNLIMITED_INSTANCES) and serves them concurrently. A connection
    //    may transiently fail with ERROR_PIPE_BUSY before the server has looped
    //    around to create the next instance, so each attempt is retried.
    std::vector<std::unique_ptr<ClientNamedPipe>> pipes;
    {
        int elapsed = 0;
        while (static_cast<int>(pipes.size()) < PIPE_POOL_SIZE
               && elapsed < RETRY_TIMEOUT_MS) {
            try {
                pipes.push_back(std::make_unique<ClientNamedPipe>(
                    65536, 65536, PIPE_NAME, /*duplex=*/true));
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

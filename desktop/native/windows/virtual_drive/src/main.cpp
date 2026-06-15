#define NOMINMAX
#include <windows.h>

#include "ClientNamedPipe.h"
#include "DriveLetterUtil.h"
#include "PipeException.h"
#include "VirtualDrive.h"
#include "WinFspUtil.h"

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>

// Pipe name SyncDose.exe exposes for VirtualDrive IPC.
static constexpr char PIPE_NAME[] = "\\\\.\\pipe\\SyncDoseVDrive";

// Retry parameters for the initial pipe connection.
static constexpr int RETRY_INTERVAL_MS = 2000;
static constexpr int RETRY_TIMEOUT_MS  = 30000;

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

    // 2. Retry-connect to SyncDose's pipe server.
    std::unique_ptr<ClientNamedPipe> pipe;
    {
        int elapsed = 0;
        while (elapsed < RETRY_TIMEOUT_MS) {
            try {
                pipe = std::make_unique<ClientNamedPipe>(
                    65536, 65536, PIPE_NAME, /*duplex=*/true);
                break;
            } catch (const PipeException&) {
                std::wcout << L"[VirtualDrive] Waiting for SyncDose...\n";
                std::this_thread::sleep_for(
                    std::chrono::milliseconds(RETRY_INTERVAL_MS));
                elapsed += RETRY_INTERVAL_MS;
            }
        }
        if (!pipe) {
            std::wcerr << L"[VirtualDrive] SyncDose not running after "
                       << (RETRY_TIMEOUT_MS / 1000) << L"s. Exiting.\n";
            CloseHandle(hMutex);
            return 1;
        }
    }
    std::wcout << L"[VirtualDrive] Connected to SyncDose.\n";

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
        VirtualDrive drive(*pipe);
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

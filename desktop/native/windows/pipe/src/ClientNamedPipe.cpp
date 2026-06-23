#define NOMINMAX
#include "ClientNamedPipe.h"
#include "PipeException.h"
#include <stdexcept>
#include <algorithm>
#include <vector>
#include <limits>

std::wstring ClientNamedPipe::StringToWstring(const std::string &str)
{
    if (str.empty())
        return std::wstring();

    int size_needed = MultiByteToWideChar(
        CP_UTF8, 0,
        str.data(), (int)str.size(),
        NULL, 0);

    if (size_needed <= 0)
        return std::wstring();

    std::wstring wString(size_needed, 0);

    MultiByteToWideChar(
        CP_UTF8, 0,
        str.data(), (int)str.size(),
        &wString[0], size_needed);

    return wString;
}

ClientNamedPipe::ClientNamedPipe(int inputBufferSize, int outputBufferSize,
                                 const std::string& pipeName, bool duplex)
{
    this->inputBufferSize  = inputBufferSize;
    this->outputBufferSize = outputBufferSize;

    // Pre-allocate the I/O event once; reused by every readExact / write call
    // to avoid a CreateEvent + CloseHandle kernel round-trip per operation.
    hIoEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!hIoEvent)
        throw PipeException("Failed to create I/O event", PipeErrorCode::ConnectionFailed);

    std::wstring w_string = StringToWstring(pipeName);

    DWORD access = duplex ? (GENERIC_READ | GENERIC_WRITE) : GENERIC_WRITE;

    hPipe = CreateFileW(
        w_string.c_str(),
        access,
        0,
        nullptr,
        OPEN_EXISTING,
        FILE_FLAG_OVERLAPPED,
        nullptr
    );

    if (hPipe != INVALID_HANDLE_VALUE)
        return;

    CloseHandle(hIoEvent);
    hIoEvent = nullptr;

    DWORD err = GetLastError();
    switch (err)
    {
    case ERROR_FILE_NOT_FOUND:
        throw PipeException("Pipe not found",               PipeErrorCode::ConnectionFailed);
    case ERROR_ACCESS_DENIED:
        throw PipeException("Access denied",                PipeErrorCode::AccessDenied);
    case ERROR_PIPE_BUSY:
        throw PipeException("Pipe busy",                    PipeErrorCode::ConnectionFailed);
    default:
        throw PipeException("Failed to create client pipe", PipeErrorCode::ConnectionFailed);
    }
}

void ClientNamedPipe::write(const std::string &data, std::optional<std::chrono::milliseconds> timeout)
{
    DWORD ms = INFINITE;
    if (timeout)
        ms = (timeout->count() > std::numeric_limits<DWORD>::max())
                 ? INFINITE
                 : static_cast<DWORD>(timeout->count());

    DWORD totalBytesWritten = 0;

    while (totalBytesWritten < (DWORD)data.size())
    {
        ResetEvent(hIoEvent);
        OVERLAPPED ov = {};
        ov.hEvent = hIoEvent;

        DWORD chunkSize = std::min(
            (DWORD)(data.size() - totalBytesWritten),
            (DWORD)outputBufferSize);

        BOOL ok = WriteFile(hPipe, data.data() + totalBytesWritten, chunkSize, nullptr, &ov);

        DWORD bytesWritten = 0;
        if (ok)
        {
            // Synchronous completion — get byte count without waiting.
            GetOverlappedResult(hPipe, &ov, &bytesWritten, FALSE);
        }
        else if (GetLastError() == ERROR_IO_PENDING)
        {
            DWORD res = WaitForSingleObject(hIoEvent, ms);
            if (res == WAIT_TIMEOUT)
            {
                CancelIoEx(hPipe, &ov);
                throw PipeException("Timeout while waiting for write", PipeErrorCode::ConnectionTimeout);
            }
            if (res != WAIT_OBJECT_0)
            {
                CancelIoEx(hPipe, &ov);
                throw PipeException("Failed to wait for write", PipeErrorCode::WriteFailed);
            }
            if (!GetOverlappedResult(hPipe, &ov, &bytesWritten, FALSE))
                throw PipeException("Overlapped write failed.", PipeErrorCode::WriteFailed);
        }
        else
        {
            throw PipeException("Failed to write to pipe.", PipeErrorCode::WriteFailed);
        }

        if (bytesWritten == 0)
            throw PipeException("No data was written to the pipe.", PipeErrorCode::WriteFailed);

        totalBytesWritten += bytesWritten;
    }
}

std::string ClientNamedPipe::readExact(size_t n,
                                       std::optional<std::chrono::milliseconds> timeout)
{
    std::string buffer;
    buffer.reserve(n);

    DWORD ms = INFINITE;
    if (timeout)
        ms = static_cast<DWORD>(
            std::min(timeout->count(), (long long)std::numeric_limits<DWORD>::max()));

    while (buffer.size() < n) {
        size_t remaining = n - buffer.size();
        std::vector<char> chunk(remaining);

        ResetEvent(hIoEvent);
        OVERLAPPED ov = {};
        ov.hEvent = hIoEvent;

        DWORD bytesRead = 0;
        BOOL ok = ReadFile(hPipe, chunk.data(), (DWORD)remaining, &bytesRead, &ov);

        if (!ok) {
            DWORD err = GetLastError();
            if (err == ERROR_BROKEN_PIPE || err == ERROR_PIPE_NOT_CONNECTED)
                throw PipeException("Pipe broken", PipeErrorCode::BrokenPipe);
            if (err != ERROR_IO_PENDING)
                throw PipeException("ReadFile failed", PipeErrorCode::ReadFailed);

            DWORD res = WaitForSingleObject(hIoEvent, ms);
            if (res == WAIT_TIMEOUT) {
                CancelIoEx(hPipe, &ov);
                throw PipeException("Timeout in readExact", PipeErrorCode::ConnectionTimeout);
            }
            if (res != WAIT_OBJECT_0)
                throw PipeException("Wait failed in readExact", PipeErrorCode::ReadFailed);

            if (!GetOverlappedResult(hPipe, &ov, &bytesRead, FALSE)) {
                DWORD err2 = GetLastError();
                throw PipeException(
                    err2 == ERROR_BROKEN_PIPE ? "Pipe broken" : "Overlapped read failed",
                    err2 == ERROR_BROKEN_PIPE ? PipeErrorCode::BrokenPipe
                                              : PipeErrorCode::ReadFailed);
            }
        }

        if (bytesRead == 0)
            throw PipeException("Zero bytes read — pipe closed", PipeErrorCode::BrokenPipe);
        buffer.append(chunk.data(), bytesRead);
    }

    return buffer;
}

void ClientNamedPipe::close()
{
    if (hPipe != INVALID_HANDLE_VALUE)
    {
        CloseHandle(hPipe);
        hPipe = INVALID_HANDLE_VALUE;
    }
    if (hIoEvent != nullptr)
    {
        CloseHandle(hIoEvent);
        hIoEvent = nullptr;
    }
}

ClientNamedPipe::~ClientNamedPipe()
{
    close();
}
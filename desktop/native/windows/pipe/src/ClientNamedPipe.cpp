#define NOMINMAX
#include "ClientNamedPipe.h"
#include "PipeException.h"
#include <stdexcept>
#include <algorithm>

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

ClientNamedPipe::ClientNamedPipe(int inputBufferSize, int outputBufferSize, const std::string &pipeName)
{
    this->inputBufferSize = inputBufferSize;
    this->outputBufferSize = outputBufferSize;

    std::wstring w_string = StringToWstring(pipeName);

    hPipe = CreateFileW(
        w_string.c_str(),
        GENERIC_WRITE,
        0,
        nullptr,
        OPEN_EXISTING,
        FILE_FLAG_OVERLAPPED,
        nullptr);

    if (hPipe != INVALID_HANDLE_VALUE)
    {
        return; // SUCCESS case
    }

    DWORD err = GetLastError();

    switch (err)
    {
    case ERROR_FILE_NOT_FOUND:
        throw PipeException("Pipe not found", PipeErrorCode::ConnectionFailed);

    case ERROR_ACCESS_DENIED:
        throw PipeException("Access denied", PipeErrorCode::AccessDenied);

    case ERROR_PIPE_BUSY:
        throw PipeException("Pipe busy", PipeErrorCode::ConnectionFailed);

    default:
        throw PipeException("Failed to create client pipe", PipeErrorCode::ConnectionFailed);
    }
}

void ClientNamedPipe::write(const std::string &data, std::optional<std::chrono::milliseconds> timeout)
{



    DWORD totalBytesWritten = 0;

    while (totalBytesWritten < (DWORD)data.size())
    {
        OVERLAPPED ov = {};
        ov.hEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);

            if (ov.hEvent == nullptr)
            throw PipeException("Failed to create event.", PipeErrorCode::WriteFailed);

        DWORD chunkSize = std::min(
            (DWORD)(data.size() - totalBytesWritten),
            (DWORD)outputBufferSize);

        BOOL ok = WriteFile(hPipe, data.data() + totalBytesWritten, chunkSize, nullptr, &ov);

        if (!ok && GetLastError() != ERROR_IO_PENDING)
        {
            CloseHandle(ov.hEvent);
            throw PipeException("Failed to write to pipe.", PipeErrorCode::WriteFailed);
        }

       DWORD ms = INFINITE;
if (timeout)
{
    ms = (timeout->count() > std::numeric_limits<DWORD>::max())
             ? INFINITE
             : static_cast<DWORD>(timeout->count());
}
        DWORD res = WaitForSingleObject(ov.hEvent, ms);

        if (res == WAIT_TIMEOUT)
        {
            CancelIoEx(hPipe, &ov);
            CloseHandle(ov.hEvent);
            throw PipeException("Timeout while waiting for client", PipeErrorCode::ConnectionTimeout);
        }
        if (res == WAIT_FAILED || res == WAIT_ABANDONED)
        {
            CancelIoEx(hPipe, &ov);
            CloseHandle(ov.hEvent);
            throw PipeException("Failed to wait for client", PipeErrorCode::WriteFailed);
        }

        DWORD bytesWritten = 0;

        if (!GetOverlappedResult(hPipe, &ov, &bytesWritten, FALSE)) {
         CloseHandle(ov.hEvent);
            throw PipeException("Overlapped write failed.", PipeErrorCode::WriteFailed);

        }
            CloseHandle(ov.hEvent);

        if (bytesWritten == 0)
        {
            throw PipeException("No data was written to the pipe.", PipeErrorCode::WriteFailed);
        }
        totalBytesWritten += bytesWritten;
    }
}

void ClientNamedPipe::close()
{
    if (hPipe != INVALID_HANDLE_VALUE)
    {
        CloseHandle(hPipe);
        hPipe = INVALID_HANDLE_VALUE;
    }
}

ClientNamedPipe::~ClientNamedPipe()
{
    close();
}
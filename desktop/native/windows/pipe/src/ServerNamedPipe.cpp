#include "ServerNamedPipe.h"
#include "PipeException.h"
#include <vector>
#include <limits>
#include <optional>

std::wstring ServerNamedPipe::StringToWstring(const std::string &str)
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

ServerNamedPipe::ServerNamedPipe(int inputBufferSize, int outputBufferSize,
                                 const std::string& pipeName, bool byte_stream)
{
    this->inputBufferSize  = inputBufferSize;
    this->outputBufferSize = outputBufferSize;

    // Pre-allocate the I/O event once; reused by every readExact / write call
    // to avoid a CreateEvent + CloseHandle kernel round-trip per operation.
    hIoEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!hIoEvent)
        throw PipeException("Failed to create I/O event", PipeErrorCode::ConnectionFailed);

    std::wstring w_string = StringToWstring(pipeName);

    DWORD pipe_mode = byte_stream
        ? (PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT)
        : (PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT);

    hPipe = CreateNamedPipeW(
        w_string.c_str(),
        PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
        pipe_mode,
        PIPE_UNLIMITED_INSTANCES,
        outputBufferSize,
        inputBufferSize,
        0,
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
        throw PipeException("Pipe not found",          PipeErrorCode::ConnectionFailed);
    case ERROR_ACCESS_DENIED:
        throw PipeException("Access denied",           PipeErrorCode::AccessDenied);
    case ERROR_PIPE_BUSY:
        throw PipeException("Pipe busy",               PipeErrorCode::ConnectionFailed);
    default:
        throw PipeException("CreateNamedPipeW failed", PipeErrorCode::ConnectionFailed);
    }
}

void ServerNamedPipe::waitForClient(std::optional<std::chrono::milliseconds> timeout)
{
    OVERLAPPED ov = {};
    ov.hEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);

    BOOL ok = ConnectNamedPipe(hPipe, &ov);


    if (ok)
    {
        CloseHandle(ov.hEvent);
        return;
    }

    DWORD err = GetLastError();


    if (err == ERROR_PIPE_CONNECTED)
{
    CloseHandle(ov.hEvent);
    return; // client already connected, success
}

    if (err != ERROR_IO_PENDING)
    {
        CloseHandle(ov.hEvent);
        throw PipeException("Failed to connect client", PipeErrorCode::ConnectionFailed);
    }

    DWORD ms = INFINITE;
    if (timeout)
    {
    ms = (timeout->count() > std::numeric_limits<DWORD>::max())
             ? INFINITE
             : static_cast<DWORD>(timeout->count());
    }

    DWORD res = WaitForSingleObject(ov.hEvent, static_cast<DWORD>(ms));

    if (res == WAIT_TIMEOUT)
    {
        CancelIoEx(hPipe, &ov);
        CloseHandle(ov.hEvent);

        throw PipeException("Timeout while waiting for client", PipeErrorCode::ConnectionTimeout);
    }
    if (res == WAIT_FAILED || res == WAIT_ABANDONED)
    {
        CloseHandle(ov.hEvent);
        throw PipeException("Failed to wait for client", PipeErrorCode::ConnectionFailed);
    }

    DWORD bytesTransferred;
    if (GetOverlappedResult(hPipe, &ov, &bytesTransferred, FALSE))
    {
        CloseHandle(ov.hEvent);
        return; // SUCCESS case
    }
    CloseHandle(ov.hEvent);
    throw PipeException("Failed to connect client", PipeErrorCode::ConnectionFailed);
}

std::string ServerNamedPipe::read(std::optional<std::chrono::milliseconds> timeout)
{

    OVERLAPPED ov = {};
    ov.hEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);
    DWORD read = 0;
    std::vector<char> buffer(this->outputBufferSize);

    BOOL ok = ReadFile(hPipe, buffer.data(), buffer.size(), &read, &ov);

    if (ok)
    {
        CloseHandle(ov.hEvent);
        return std::string(buffer.data(), read);
    }

    DWORD err = GetLastError();

    if (err != ERROR_IO_PENDING)
    {
        CloseHandle(ov.hEvent);
        throw PipeException("Failed to connect client", PipeErrorCode::ConnectionFailed);
    }
    DWORD ms = (timeout && timeout->count() > std::numeric_limits<DWORD>::max()) ? INFINITE
                                                                                 : static_cast<DWORD>(timeout->count());

    DWORD res = WaitForSingleObject(ov.hEvent, ms);
    if (res == WAIT_TIMEOUT)
    {
        CancelIoEx(hPipe, &ov);
        CloseHandle(ov.hEvent);
        throw PipeException("Timeout while waiting for client", PipeErrorCode::ConnectionTimeout);
    }

    if (res == WAIT_FAILED || res == WAIT_ABANDONED)
    {
        CloseHandle(ov.hEvent);
        throw PipeException("Failed to wait for client", PipeErrorCode::ReadFailed);
    }
    if (!GetOverlappedResult(hPipe, &ov, &read, FALSE))
    {
        CloseHandle(ov.hEvent);
        throw PipeException("Failed to read from pipe", PipeErrorCode::ReadFailed);
    }
    CloseHandle(ov.hEvent);
    return std::string(buffer.data(), read);
}

void ServerNamedPipe::close()
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

void ServerNamedPipe::disconnect()
{
    DisconnectNamedPipe(hPipe);
}

std::string ServerNamedPipe::readExact(size_t n,
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

void ServerNamedPipe::write(const std::string& data,
                            std::optional<std::chrono::milliseconds> timeout)
{
    DWORD ms = INFINITE;
    if (timeout)
        ms = static_cast<DWORD>(
            std::min(timeout->count(), (long long)std::numeric_limits<DWORD>::max()));

    DWORD totalWritten = 0;

    while (totalWritten < (DWORD)data.size()) {
        ResetEvent(hIoEvent);
        OVERLAPPED ov = {};
        ov.hEvent = hIoEvent;

        DWORD chunkSize = static_cast<DWORD>(
            std::min((size_t)(data.size() - totalWritten),
                     (size_t)outputBufferSize));

        BOOL ok = WriteFile(hPipe, data.data() + totalWritten, chunkSize, nullptr, &ov);

        DWORD bytesWritten = 0;
        if (ok)
        {
            // Synchronous completion — get byte count without waiting.
            GetOverlappedResult(hPipe, &ov, &bytesWritten, FALSE);
        }
        else if (GetLastError() == ERROR_IO_PENDING)
        {
            DWORD res = WaitForSingleObject(hIoEvent, ms);
            if (res == WAIT_TIMEOUT) {
                CancelIoEx(hPipe, &ov);
                throw PipeException("Timeout in write", PipeErrorCode::ConnectionTimeout);
            }
            if (res != WAIT_OBJECT_0)
                throw PipeException("Wait failed in write", PipeErrorCode::WriteFailed);

            if (!GetOverlappedResult(hPipe, &ov, &bytesWritten, FALSE))
                throw PipeException("Overlapped write failed", PipeErrorCode::WriteFailed);
        }
        else
        {
            throw PipeException("WriteFile failed", PipeErrorCode::WriteFailed);
        }

        if (bytesWritten == 0)
            throw PipeException("Zero bytes written", PipeErrorCode::WriteFailed);
        totalWritten += bytesWritten;
    }
}

ServerNamedPipe::~ServerNamedPipe()
{
    disconnect();
    close();
}

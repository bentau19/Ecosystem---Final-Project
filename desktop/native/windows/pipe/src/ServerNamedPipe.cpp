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

ServerNamedPipe::ServerNamedPipe(int inputBufferSize, int outputBufferSize, const std::string &pipeName)
{
    this->inputBufferSize = inputBufferSize;
    this->outputBufferSize = outputBufferSize;
    std::wstring w_string = StringToWstring(pipeName);

    hPipe = CreateNamedPipeW(
        w_string.c_str(),
        PIPE_ACCESS_DUPLEX|FILE_FLAG_OVERLAPPED,
        PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
        1,                // Max instances
        outputBufferSize, // Output buffer size
        inputBufferSize,  // Input buffer size
        0,                // Default timeout
        nullptr           // Default security attributes
    );

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
}

void ServerNamedPipe::disconnect()
{
    DisconnectNamedPipe(hPipe);
}

ServerNamedPipe::~ServerNamedPipe()
{
    disconnect();
    close();
}

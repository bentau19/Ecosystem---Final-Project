#pragma once
#define NOMINMAX
#include <string>
#include <windows.h>
#include <chrono>
#include <optional>

using namespace std;

class ServerNamedPipe
{
private:
    HANDLE hPipe;
    HANDLE hIoEvent;  // pre-allocated, reused for all overlapped I/O
    int inputBufferSize;
    int outputBufferSize;
    std::wstring StringToWstring(const std::string& str);

public:
    // byte_stream=false  ->  PIPE_TYPE_MESSAGE (existing FileSend behaviour, unchanged)
    // byte_stream=true   ->  PIPE_TYPE_BYTE    (required for VirtualDrive IPC)
    ServerNamedPipe(int inputBufferSize, int outputBufferSize,
                    const std::string& pipeName, bool byte_stream = false);

    void waitForClient(std::optional<std::chrono::milliseconds> timeout = std::nullopt);

    // Read one message (message-mode) or up to buffer size (byte-stream).
    std::string read(std::optional<std::chrono::milliseconds> timeout = std::nullopt);

    // Read exactly n bytes — use this for byte-stream frame parsing.
    std::string readExact(size_t n,
                          std::optional<std::chrono::milliseconds> timeout = std::nullopt);

    // Write data to the connected client.
    void write(const std::string& data,
               std::optional<std::chrono::milliseconds> timeout = std::nullopt);

    void disconnect();
    void close();
    ~ServerNamedPipe();
};

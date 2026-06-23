#pragma once
#define NOMINMAX
#include <string>
#include <windows.h>
#include <chrono>
#include <optional>

using namespace std;

class ClientNamedPipe
{
private:
    HANDLE hPipe;
    HANDLE hIoEvent;  // pre-allocated, reused for all overlapped I/O
    int inputBufferSize;
    int outputBufferSize;
    std::wstring StringToWstring(const std::string& str);

public:
    // duplex=false  ->  GENERIC_WRITE only  (existing FileHandler behaviour, unchanged)
    // duplex=true   ->  GENERIC_READ | GENERIC_WRITE  (required for VirtualDrive —
    //                   sends requests AND reads responses over the same handle)
    ClientNamedPipe(int inputBufferSize, int outputBufferSize,
                    const std::string& pipeName, bool duplex = false);

    void write(const std::string& data,
               std::optional<std::chrono::milliseconds> timeout = std::nullopt);

    // Read exactly n bytes — use this for byte-stream frame parsing.
    // Only meaningful when constructed with duplex=true.
    std::string readExact(size_t n,
                          std::optional<std::chrono::milliseconds> timeout = std::nullopt);

    void close();
    ~ClientNamedPipe();
};
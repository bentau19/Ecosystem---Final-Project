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
    int inputBufferSize;
    int outputBufferSize;
    std::wstring StringToWstring(const std::string &str);

public:
    ServerNamedPipe(int inputBufferSize, int outputBufferSize, const std::string &pipeName);
    void waitForClient(std::optional<std::chrono::milliseconds> timeout = std::nullopt);
    std::string read(std::optional<std::chrono::milliseconds> timeout = std::nullopt);
    void disconnect();
    void close();
    ~ServerNamedPipe();
};

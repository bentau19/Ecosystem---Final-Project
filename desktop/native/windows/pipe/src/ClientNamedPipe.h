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
        int inputBufferSize;
        int outputBufferSize;
        std::wstring StringToWstring(const std::string& str);
    public:
        ClientNamedPipe(int inputBufferSize, int outputBufferSize, const std::string &pipeName);
        void write(const std::string& data, std::optional<std::chrono::milliseconds> timeout = std::nullopt);
        void close();
        ~ClientNamedPipe();

};
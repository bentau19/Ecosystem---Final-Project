#pragma once
#include <string>
#include <windows.h>

using namespace std;
class ServerNamedPipe
{
private:
    HANDLE hPipe;
    int inputBufferSize;
    int outputBufferSize;
    std::wstring StringToWstring(const std::string& str);

public:
    ServerNamedPipe(int inputBufferSize, int outputBufferSize, const std::string &pipeName);
    void waitForClient();
    std::string read();
    void disconnect();
    void close();
    ~ServerNamedPipe();
};

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

public:
    ServerNamedPipe(int inputBufferSize, int outputBufferSize, const std::wstring &pipeName);
    void waitForClient();
    std::string read();
    void disconnect();
    void close();
    ~ServerNamedPipe();
};

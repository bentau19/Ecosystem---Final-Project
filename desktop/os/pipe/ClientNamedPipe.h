#pragma once
#include <string>
#include <windows.h>

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
        void write(const std::string& data);
        void close();
        ~ClientNamedPipe();

};
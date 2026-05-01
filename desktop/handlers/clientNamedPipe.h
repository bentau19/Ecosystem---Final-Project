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
    public:
        ClientNamedPipe(int inputBufferSize, int outputBufferSize, const std::wstring &pipeName);
        void write(const std::string& data);
        void close();
        void disconnect();
        ~ClientNamedPipe(); 

};
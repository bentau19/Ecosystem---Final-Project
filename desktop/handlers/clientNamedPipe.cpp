#include "clientNamedPipe.h"

#include <stdexcept>

ClientNamedPipe::ClientNamedPipe(int inputBufferSize, int outputBufferSize, const std::wstring &pipeName)
{
    this->inputBufferSize = inputBufferSize;
    this->outputBufferSize = outputBufferSize;
    hPipe = CreateFileW(
        pipeName.c_str(),
        GENERIC_READ | GENERIC_WRITE,
        0,
        nullptr,
        OPEN_EXISTING,
        0,
        nullptr);

    if (hPipe == INVALID_HANDLE_VALUE)
    {
        throw std::runtime_error("Failed to create named pipe.");
    }
}

void ClientNamedPipe::write(const std::string& data)
{
    DWORD totalBytesWritten = 0;

    while (totalBytesWritten < data.length())
    {
        DWORD bytesWritten = 0;
        DWORD chunkSize = min((int)(data.length() - totalBytesWritten), outputBufferSize);
        if (!WriteFile(hPipe, data.data() + totalBytesWritten, chunkSize, &bytesWritten, nullptr))
        {
            throw std::runtime_error("Failed to write to pipe.");
        }

        if (bytesWritten == 0)
        {
            throw std::runtime_error("No data was written to the pipe.");
        }

        totalBytesWritten += bytesWritten;
    }
}

void ClientNamedPipe::close()
{
    if (hPipe != INVALID_HANDLE_VALUE)
    {
        CloseHandle(hPipe);
        hPipe = INVALID_HANDLE_VALUE;
    }
}

void ClientNamedPipe::disconnect()
{
    DisconnectNamedPipe(hPipe);
}

ClientNamedPipe::~ClientNamedPipe()
{
    disconnect();
    close();
}

int main(int argc, char const *argv[])
{
    ClientNamedPipe client(512, 512, L"\\\\.\\pipe\\MyPipe");
    client.write("Hello from client!");
    client.disconnect();
    client.close();
    return 0;
}

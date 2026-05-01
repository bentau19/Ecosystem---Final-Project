    #include "serverNamedPipe.h"
    #include <ostream>
    #include <iostream>
    #include <vector>


    ServerNamedPipe::ServerNamedPipe(int inputBufferSize, int outputBufferSize, const std::wstring &pipeName)
    {
        hPipe = CreateNamedPipeW(
            pipeName.c_str(),
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            1,      // Max instances
            outputBufferSize,  // Output buffer size
            inputBufferSize,  // Input buffer size
            0,      // Default timeout
            nullptr // Default security attributes
        );

        if (hPipe == INVALID_HANDLE_VALUE)
        {
            throw std::runtime_error("Failed to create named pipe.");
        }
    }

    void ServerNamedPipe::waitForClient()
    {
        if (!ConnectNamedPipe(hPipe, nullptr) && GetLastError() != ERROR_PIPE_CONNECTED)
        {
            throw std::runtime_error("Failed to connect to client.");
        }
    }


    std::string ServerNamedPipe::read()
    {
        DWORD read = 0;
        std::vector<char> buffer(this->outputBufferSize);
        if (!ReadFile(hPipe, buffer.data(), buffer.size(), &read, nullptr))
        {
            throw std::runtime_error("Read failed");
        }
        if (read == 0)
        {
            throw std::runtime_error("No data read from pipe");
        }

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



   
    int main(int argc, char const *argv[])
    {
        std::cout << "Waiting for client to connect..." << std::endl;
        ServerNamedPipe server(512, 512, L"\\\\.\\pipe\\MyPipe");
        server.waitForClient();
        std::string message = server.read();
        std::cout << "Received message: " << message << std::endl;
        server.disconnect();
        server.close();

        return 0;
    }

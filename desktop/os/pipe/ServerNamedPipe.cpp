    #include "ServerNamedPipe.h"
    #include "PipeException.h"
    #include <vector>
std::wstring ServerNamedPipe::StringToWstring(const std::string& str) {
     if (str.empty()) return std::wstring();

    int size_needed = MultiByteToWideChar(
        CP_UTF8, 0,
        str.data(), (int)str.size(),
        NULL, 0
    );

    if (size_needed <= 0)
        return std::wstring();

    std::wstring wString(size_needed, 0);

    MultiByteToWideChar(
        CP_UTF8, 0,
        str.data(), (int)str.size(),
        &wString[0], size_needed
    );

    return wString;

}

    ServerNamedPipe::ServerNamedPipe(int inputBufferSize, int outputBufferSize, const std::string &pipeName)
    {
        this->inputBufferSize = inputBufferSize;
        this->outputBufferSize = outputBufferSize;
        std::wstring w_string = StringToWstring(pipeName);

        hPipe = CreateNamedPipeW(
            w_string.c_str(),
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            1,      // Max instances
            outputBufferSize,  // Output buffer size
            inputBufferSize,  // Input buffer size
            0,      // Default timeout
            nullptr // Default security attributes
        );


            if (hPipe != INVALID_HANDLE_VALUE){
            return; // SUCCESS case
            }
    DWORD err = GetLastError();

    switch (err)
{
    case ERROR_FILE_NOT_FOUND:
        throw PipeException("Pipe not found", PipeErrorCode::ConnectionFailed);

    case ERROR_ACCESS_DENIED:
        throw PipeException("Access denied", PipeErrorCode::AccessDenied);

    case ERROR_PIPE_BUSY:
        throw PipeException("Pipe busy", PipeErrorCode::ConnectionFailed);
}
    }

    void ServerNamedPipe::waitForClient()
    {
      BOOL ok = ConnectNamedPipe(hPipe, nullptr);

    if (ok)
    {
        return;
    }

    DWORD err = GetLastError();

    if (err == ERROR_PIPE_CONNECTED)
        return; // SUCCESS case

    if (err == ERROR_NO_DATA)
        throw PipeException("Client disconnected during connect",
                            PipeErrorCode::BrokenPipe);

    throw PipeException("Failed to connect client",
                        PipeErrorCode::ConnectionFailed);
}



    std::string ServerNamedPipe::read()
    {
        DWORD read = 0;
        std::vector<char> buffer(this->outputBufferSize);
        if (!ReadFile(hPipe, buffer.data(), buffer.size(), &read, nullptr))
        {
            throw PipeException("Read failed", PipeErrorCode::ReadFailed);
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

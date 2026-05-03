
#pragma once

#include <stdexcept>

enum class PipeErrorCode {
    ConnectionFailed,
    Disconnected,
    Timeout,
    AccessDenied,
    ReadFailed,
    WriteFailed,
    BrokenPipe
};


class PipeException : public std::runtime_error {
public:
    PipeErrorCode code;

    PipeException(std::string msg, PipeErrorCode c)
        : std::runtime_error(msg), code(c) {}
};

#pragma once

#include <stdexcept>

enum class PipeErrorCode
{
    ConnectionFailed,
    ConnectionTimeout,
    Disconnected,
    Timeout,
    AccessDenied,
    ReadFailed,
    WriteFailed,
    BrokenPipe
};

enum class PipeErrorCategory
{
    Connection, ///< server not reachable — pipe was never opened
    Transfer,   ///< pipe was open; failure occurred during I/O
    Timeout     // pipe was open, but no data was transferred within the timeout
};

class PipeException : public std::runtime_error
{
public:
    PipeErrorCode code;

    PipeException(std::string msg, PipeErrorCode c)
        : std::runtime_error(msg), code(c) {}

    /// Returns the coarse category for this error code.
    PipeErrorCategory category() const noexcept
    {
        switch (code)
        {
        case PipeErrorCode::ConnectionFailed:
        case PipeErrorCode::AccessDenied:
        case PipeErrorCode::Timeout:
            return PipeErrorCategory::Connection;

        case PipeErrorCode::WriteFailed:
        case PipeErrorCode::ReadFailed:
        case PipeErrorCode::BrokenPipe:
        case PipeErrorCode::Disconnected:
        case PipeErrorCode::ConnectionTimeout:
            return PipeErrorCategory::Timeout;
        default:
            return PipeErrorCategory::Transfer;
        }
    }
};
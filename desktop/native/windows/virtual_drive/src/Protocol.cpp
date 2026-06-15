#define NOMINMAX
#include <windows.h>

#include "Protocol.h"
#include "ClientNamedPipe.h"

#include <cstring>
#include <limits>

namespace protocol {

// ── Internal helpers ──────────────────────────────────────────────────────────

// Read the next 4 bytes from the pipe and interpret them as a LE uint32.
static uint32_t readU32LE(ClientNamedPipe& pipe)
{
    std::string raw = pipe.readExact(4);
    uint32_t value = 0;
    std::memcpy(&value, raw.data(), 4);
    // Windows is always little-endian — no byte-swap needed.
    return value;
}

// Append value as 4 LE bytes into dest.
static void writeU32LE(std::string& dest, uint32_t value)
{
    char buf[4];
    std::memcpy(buf, &value, 4);
    dest.append(buf, 4);
}

// ── Public API ────────────────────────────────────────────────────────────────

void writeFrame(ClientNamedPipe& pipe, const Message& msg)
{
    // Assemble the entire frame into one buffer so WriteFile sees it as a single
    // chunk — avoids the Python server receiving a partial frame on slow paths.
    std::string frame;
    frame.reserve(8 + msg.json.size() + msg.payload.size());

    writeU32LE(frame, static_cast<uint32_t>(msg.json.size()));
    frame.append(msg.json);
    writeU32LE(frame, static_cast<uint32_t>(msg.payload.size()));
    frame.append(msg.payload);

    pipe.write(frame);
}

Message readFrame(ClientNamedPipe& pipe)
{
    Message msg;

    uint32_t json_len = readU32LE(pipe);
    msg.json          = pipe.readExact(json_len);

    uint32_t payload_len = readU32LE(pipe);
    if (payload_len > 0)
        msg.payload = pipe.readExact(payload_len);

    return msg;
}

Message send(ClientNamedPipe& pipe, const Message& request)
{
    writeFrame(pipe, request);
    return readFrame(pipe);
}

}

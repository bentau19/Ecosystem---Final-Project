#define NOMINMAX
#include <windows.h>

#include "Protocol.h"
#include "ClientNamedPipe.h"

#include <cstring>
#include <limits>

namespace protocol {

// ── Internal helpers ──────────────────────────────────────────────────────────

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
    // Frame layout: [4B json_len][4B payload_len][json bytes][payload bytes]
    // Both lengths are packed first so the reader can coalesce them into a
    // single 8-byte readExact instead of two separate 4-byte reads.
    std::string frame;
    frame.reserve(8 + msg.json.size() + msg.payload.size());

    writeU32LE(frame, static_cast<uint32_t>(msg.json.size()));
    writeU32LE(frame, static_cast<uint32_t>(msg.payload.size()));
    frame.append(msg.json);
    frame.append(msg.payload);

    pipe.write(frame);
}

Message readFrame(ClientNamedPipe& pipe)
{
    // Read both length prefixes in one call — writeFrame always sends the whole
    // frame atomically, so all bytes are in the kernel buffer by the time the
    // first byte is readable.  Two readExact calls instead of three or four.
    std::string hdr = pipe.readExact(8);
    uint32_t json_len    = 0;
    uint32_t payload_len = 0;
    std::memcpy(&json_len,    hdr.data(),     4);
    std::memcpy(&payload_len, hdr.data() + 4, 4);

    Message msg;
    if (json_len + payload_len > 0) {
        std::string body = pipe.readExact(json_len + payload_len);
        msg.json    = body.substr(0, json_len);
        msg.payload = payload_len ? body.substr(json_len) : std::string{};
    }
    return msg;
}

Message send(ClientNamedPipe& pipe, const Message& request)
{
    writeFrame(pipe, request);
    return readFrame(pipe);
}

}

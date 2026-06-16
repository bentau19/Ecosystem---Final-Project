#pragma once
#include <string>
#include <cstdint>

// ── IPC protocol between VirtualDrive.exe (client) and SyncDose.exe (server) ──
//
// Transport: Windows named pipe  \\.\pipe\SyncDoseVDrive  (duplex, byte mode).
//
// Every request and every response is a single MESSAGE composed of two
// length-prefixed frames laid out back to back:
//
//     [4B LE jsonLen][4B LE payloadLen][json bytes][payload bytes]
//
// Both lengths are packed first so readers can coalesce them into a single
// 8-byte read instead of two separate 4-byte reads.
//
//   • json    — UTF-8 JSON object.  Request: {"op": "...", ...}.
//                Response: {"ok": true|false, "error": "...", ...op-specific...}.
//   • payload — raw file bytes.  Held in a std::string used purely as a byte
//                buffer (always accessed via .data()/.size(), never .c_str(),
//                so embedded NUL bytes are preserved).  Empty for most ops;
//                carries data for read responses and write requests.
//
// Operations ("op" field):
//   "list"        {path}                  -> {ok, entries:[{name,is_dir,size,mtime_ms}]}
//   "stat"        {path}                  -> {ok, name,is_dir,size,mtime_ms} | {ok:false}
//   "read"        {path,offset,length}    -> {ok} + payload(file bytes)
//   "write_open"  {path}                  -> {ok}
//   "write"       {path,offset} + payload -> {ok}
//   "write_close" {path}                  -> {ok}
//   "create"      {path,is_dir}           -> {ok}
//   "delete"      {path}                  -> {ok}
//   "rename"      {from,to}               -> {ok}
//   "truncate"    {path,new_size}         -> {ok}

// Forward declaration — Protocol.cpp includes ClientNamedPipe.h directly.
class ClientNamedPipe;

namespace protocol {

// Default pipe name shared by both processes.
inline constexpr const wchar_t* PIPE_NAME = L"\\\\.\\pipe\\SyncDoseVDrive";

// One protocol message: a JSON header plus an optional raw-byte payload.
struct Message {
    std::string json;
    std::string payload;   // raw bytes — use .data()/.size(), never .c_str()
};

// Write a framed Message to the pipe.
void writeFrame(ClientNamedPipe& pipe, const Message& msg);

// Block until a complete framed Message is read from the pipe.
Message readFrame(ClientNamedPipe& pipe);

// Convenience: write request, block for response. One synchronous round-trip.
Message send(ClientNamedPipe& pipe, const Message& request);

}  // namespace protocol

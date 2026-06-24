#pragma once
#include <string>
#include <cstdint>
#include <chrono>
#include <optional>

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
//   "list"        {path}                    -> {ok, entries:[{name,is_dir,size,mtime_ms}]}
//   "list_page"   {path,after,limit}        -> {ok, entries:[...], has_more, next_after}
//   "stat"        {path}                    -> {ok, name,is_dir,size,mtime_ms} | {ok:false}
//   "read"        {path,offset,length}      -> {ok} + payload(file bytes)   [one-shot channel]
//   "read"        {session,offset,length}   -> {ok} + payload(file bytes)   [persistent session]
//   "read_open"   {path}                    -> {ok, session}   open a persistent read channel
//   "read_close"  {session}                 -> {ok}            close a persistent read channel
//   "write_open"  {path}                    -> {ok}
//   "write"       {path,offset} + payload   -> {ok}
//   "write_close" {path}                    -> {ok}
//   "create"      {path,is_dir}             -> {ok}
//   "delete"      {path}                    -> {ok}
//   "rename"      {from,to}                 -> {ok}
//   "truncate"    {path,new_size}           -> {ok}
//
// Persistent read sessions: read_open establishes ONE long-lived TauSync channel
// per open streaming (video) file handle; the handle then issues many `read`
// {session,offset,length} ops reused over it and a final read_close. This pays
// the channel handshake + Android file-open once per handle instead of per fetch.
// A `read` with {path} (no session) keeps the one-shot behaviour for ordinary files.

// Forward declaration — Protocol.cpp includes ClientNamedPipe.h directly.
class ClientNamedPipe;

namespace protocol {

// Pipe name shared by both processes — wide for FspFileSystemSetMountPoint / CreateFile
// paths in Win32 APIs that accept PWSTR, narrow for ClientNamedPipe's const char* constructor.
inline constexpr const wchar_t* PIPE_NAME   = L"\\\\.\\pipe\\SyncDoseVDrive";
inline constexpr const char*    PIPE_NAME_A =  "\\\\.\\pipe\\SyncDoseVDrive";

// Named-pipe read/write buffer size (bytes). Both sides use the same value so the
// kernel can use the pre-allocated buffer without a copy on a single-chunk write.
inline constexpr int PIPE_BUFFER_SIZE = 65536;

// One protocol message: a JSON header plus an optional raw-byte payload.
struct Message {
    std::string json;
    std::string payload;   // raw bytes — use .data()/.size(), never .c_str()
};

// Write a framed Message to the pipe. An optional timeout bounds each blocking
// pipe write; std::nullopt means block indefinitely (the historical behaviour).
void writeFrame(ClientNamedPipe& pipe, const Message& msg,
                std::optional<std::chrono::milliseconds> timeout = std::nullopt);

// Block until a complete framed Message is read from the pipe. The optional
// timeout bounds each underlying readExact; on expiry ClientNamedPipe throws a
// PipeException with code ConnectionTimeout.
Message readFrame(ClientNamedPipe& pipe,
                  std::optional<std::chrono::milliseconds> timeout = std::nullopt);

// Convenience: write request, block for response. One synchronous round-trip.
// The timeout (if given) is applied to both the write and the response read.
Message send(ClientNamedPipe& pipe, const Message& request,
             std::optional<std::chrono::milliseconds> timeout = std::nullopt);

}  // namespace protocol

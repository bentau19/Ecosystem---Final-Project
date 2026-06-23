#pragma once
#include <string>

// UTF-8 <-> wide string conversions (WinFsp uses WCHAR throughout).
std::string  WcharToUtf8(const wchar_t* w);
std::wstring Utf8ToWchar(const std::string& s);

// Normalise a raw WinFsp path to a canonical virtual path:
//   ""        -> "/"
//   "\\"      -> "/"
//   "\\Foo"   -> "/Foo"
//   "\\A\\B"  -> "/A/B"
// Result always starts with '/' and never ends with '/'.
void NormalizeVPath(std::string& path);

// Convert Unix epoch milliseconds to Windows FILETIME (100-ns ticks since 1601-01-01).
// Returns 0 when ms == 0 (unknown time).
UINT64 MsToFileTime(UINT64 ms);

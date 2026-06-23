#define NOMINMAX
#include <windows.h>

#include "WinFspUtil.h"
#include <algorithm>
#include <stdexcept>

std::string WcharToUtf8(const wchar_t* w) {
    if (!w || *w == L'\0') return {};
    int len = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr);
    if (len <= 0) return {};
    std::string result(len - 1, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w, -1, result.data(), len, nullptr, nullptr);
    return result;
}

std::wstring Utf8ToWchar(const std::string& s) {
    if (s.empty()) return {};
    int len = MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), nullptr, 0);
    if (len <= 0) return {};
    std::wstring result(len, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), result.data(), len);
    return result;
}

void NormalizeVPath(std::string& path) {
    // WinFsp passes backslash-separated paths starting with "\"
    std::replace(path.begin(), path.end(), '\\', '/');

    // Collapse multiple leading slashes to one
    if (path.empty()) {
        path = "/";
    } else if (path[0] != '/') {
        path.insert(0, 1, '/');
    }

    // Strip trailing slash (unless root)
    while (path.size() > 1 && path.back() == '/')
        path.pop_back();
}

// Unix epoch ms → Windows FILETIME (100-ns intervals since 1601-01-01 UTC)
// Offset: 11644473600 seconds between 1601-01-01 and 1970-01-01
UINT64 MsToFileTime(UINT64 ms) {
    if (ms == 0) return 0;
    return (ms + 11644473600000ULL) * 10000ULL;  // ms → 100-ns ticks
}

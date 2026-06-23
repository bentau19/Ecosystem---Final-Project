#define NOMINMAX
#include <windows.h>

#include "DriveLetterUtil.h"
#include <stdexcept>

std::string FindFirstAvailableDriveLetter() {
    DWORD drives = GetLogicalDrives();
    // Start at D: (index 3), skip A:/B:/C:
    for (int i = 3; i < 26; ++i) {
        if (!(drives & (1u << i))) {
            char letter = static_cast<char>('A' + i);
            return std::string(1, letter) + ":";  // e.g. "E:"
        }
    }
    throw std::runtime_error("No available drive letters D–Z");
}

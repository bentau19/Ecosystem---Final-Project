#pragma once
#include <string>

// Returns the first unused drive letter from D onward (e.g. "E:").
// Throws std::runtime_error if all letters D–Z are taken.
std::string FindFirstAvailableDriveLetter();

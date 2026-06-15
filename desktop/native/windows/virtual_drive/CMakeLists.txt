cmake_minimum_required(VERSION 3.15)

# Force the Visual Studio generator's toolset detection before project() runs.
# Without this, CMake on Windows defaults to NMake and fails if nmake.exe is
# not on PATH (i.e. outside a VS developer prompt).
if(NOT DEFINED CMAKE_GENERATOR AND WIN32)
    set(CMAKE_GENERATOR "Visual Studio 17 2022" CACHE STRING "" FORCE)
    set(CMAKE_GENERATOR_PLATFORM "x64"          CACHE STRING "" FORCE)
endif()

project(VirtualDrive LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── Standalone executable (Option B) ─────────────────────────────────────────
# VirtualDrive.exe contains NO Python and NO pybind11.  It is a pure C++ process
# that mounts a WinFsp filesystem and forwards every operation to SyncDose.exe
# over a Windows named pipe (\\.\pipe\SyncDoseVDrive).  Same "separate helper
# exe" pattern as FileHandler.exe.
#
# ClientNamedPipe.cpp is shared directly from ../pipe/src/ — it is plain C++
# with no Python dependency, so it compiles cleanly into this executable.

include(FetchContent)

# nlohmann/json — header-only JSON for the IPC protocol.
FetchContent_Declare(
    nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG        v3.11.3
    GIT_SHALLOW    TRUE
)
FetchContent_MakeAvailable(nlohmann_json)

# WinFsp headers — downloaded from GitHub at configure time.
FetchContent_Declare(
    winfsp
    GIT_REPOSITORY https://github.com/winfsp/winfsp.git
    GIT_TAG        v2.0
    GIT_SHALLOW    TRUE
)
FetchContent_GetProperties(winfsp)
if(NOT winfsp_POPULATED)
    FetchContent_Populate(winfsp)
endif()

# ── WinFsp import library ─────────────────────────────────────────────────────
# The fetched WinFsp *source* repo only ships the fsext extension stub under
# opt/fsext/lib/ — it does NOT contain the core user-mode FspFileSystem* import
# library (that lives in the separate WinFsp *developer* SDK). To avoid requiring
# the SDK, we generate an import library directly from the installed WinFsp
# *runtime* DLL's exports, and link it via delay-load. At runtime FspLoad() (see
# main.cpp) locates and loads winfsp-x64.dll through the registry InstallDir.

# Locate the installed WinFsp runtime DLL via the registry, with a fallback to
# the conventional install path.
get_filename_component(VIRTUAL_DRIVE_WINFSP_DIR
    "[HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432Node\\WinFsp;InstallDir]" ABSOLUTE)
if(NOT VIRTUAL_DRIVE_WINFSP_DIR OR NOT EXISTS "${VIRTUAL_DRIVE_WINFSP_DIR}/bin/winfsp-x64.dll")
    set(VIRTUAL_DRIVE_WINFSP_DIR "$ENV{ProgramFiles\(x86\)}/WinFsp")
endif()
set(VIRTUAL_DRIVE_WINFSP_DLL "${VIRTUAL_DRIVE_WINFSP_DIR}/bin/winfsp-x64.dll")
if(NOT EXISTS "${VIRTUAL_DRIVE_WINFSP_DLL}")
    message(FATAL_ERROR
        "WinFsp runtime not found. Install WinFsp from https://winfsp.dev "
        "(expected ${VIRTUAL_DRIVE_WINFSP_DLL}).")
endif()
message(STATUS "WinFsp DLL: ${VIRTUAL_DRIVE_WINFSP_DLL}")

# dumpbin.exe and lib.exe live alongside the MSVC compiler.
get_filename_component(VIRTUAL_DRIVE_MSVC_BIN "${CMAKE_CXX_COMPILER}" DIRECTORY)
find_program(VIRTUAL_DRIVE_DUMPBIN dumpbin HINTS "${VIRTUAL_DRIVE_MSVC_BIN}" REQUIRED)
find_program(VIRTUAL_DRIVE_LIB     lib     HINTS "${VIRTUAL_DRIVE_MSVC_BIN}" REQUIRED)

# Generate winfsp-x64.lib from the DLL's exports (configure time, so it exists
# before linking). dumpbin lists exports as: <ordinal> <hint> <RVA> <name>.
set(VIRTUAL_DRIVE_WINFSP_LIB "${CMAKE_BINARY_DIR}/winfsp_implib/winfsp-x64.lib")
set(VIRTUAL_DRIVE_WINFSP_DEF "${CMAKE_BINARY_DIR}/winfsp_implib/winfsp-x64.def")
file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/winfsp_implib")

execute_process(
    COMMAND "${VIRTUAL_DRIVE_DUMPBIN}" /exports "${VIRTUAL_DRIVE_WINFSP_DLL}"
    OUTPUT_VARIABLE _vd_exports
    RESULT_VARIABLE _vd_dumpbin_rc)
if(NOT _vd_dumpbin_rc EQUAL 0)
    message(FATAL_ERROR "dumpbin /exports failed on ${VIRTUAL_DRIVE_WINFSP_DLL}")
endif()

string(REPLACE "\n" ";" _vd_lines "${_vd_exports}")
set(_vd_def "EXPORTS\n")
set(_vd_count 0)
foreach(_vd_line IN LISTS _vd_lines)
    if(_vd_line MATCHES "^ +[0-9]+ +[0-9A-Fa-f]+ +[0-9A-Fa-f]+ +([A-Za-z_][A-Za-z0-9_]*)")
        string(APPEND _vd_def "    ${CMAKE_MATCH_1}\n")
        math(EXPR _vd_count "${_vd_count}+1")
    endif()
endforeach()
if(_vd_count EQUAL 0)
    message(FATAL_ERROR "Parsed 0 exports from ${VIRTUAL_DRIVE_WINFSP_DLL}")
endif()
file(WRITE "${VIRTUAL_DRIVE_WINFSP_DEF}" "${_vd_def}")
message(STATUS "WinFsp exports parsed: ${_vd_count}")

execute_process(
    COMMAND "${VIRTUAL_DRIVE_LIB}"
        "/def:${VIRTUAL_DRIVE_WINFSP_DEF}"
        "/out:${VIRTUAL_DRIVE_WINFSP_LIB}"
        /machine:x64 /nologo
    RESULT_VARIABLE _vd_lib_rc
    OUTPUT_VARIABLE _vd_lib_out
    ERROR_VARIABLE  _vd_lib_out)
if(NOT _vd_lib_rc EQUAL 0)
    message(FATAL_ERROR "lib /def failed: ${_vd_lib_out}")
endif()
message(STATUS "WinFsp import lib: ${VIRTUAL_DRIVE_WINFSP_LIB}")

add_executable(VirtualDrive
    src/main.cpp
    src/VirtualDrive.cpp
    src/Protocol.cpp                        # frame helpers (writeFrame/readFrame/send)
    src/DriveLetterUtil.cpp
    src/WinFspUtil.cpp
    ../pipe/src/ClientNamedPipe.cpp         # shared C++ source — no Python, no pybind11
)

target_include_directories(VirtualDrive PRIVATE
    "${winfsp_SOURCE_DIR}/inc"              # winfsp/winfsp.h
    "../pipe/src"                           # ClientNamedPipe.h, PipeException.h
)

target_link_libraries(VirtualDrive PRIVATE
    ${VIRTUAL_DRIVE_WINFSP_LIB}
    delayimp                                # delay-load helper (__delayLoadHelper2)
    nlohmann_json::nlohmann_json
)

# Delay-load winfsp-x64.dll: the loader must NOT resolve it at process start
# (it is not on PATH). FspLoad(0) in main.cpp loads it from the registry-located
# install dir before the first Fsp* call, which resolves the delay-load thunks.
target_link_options(VirtualDrive PRIVATE "/DELAYLOAD:winfsp-x64.dll")

target_compile_definitions(VirtualDrive PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN
    # NOMINMAX is #define'd at the top of every source file; omitting it here
    # prevents the C4005 "macro redefinition" warning.
)

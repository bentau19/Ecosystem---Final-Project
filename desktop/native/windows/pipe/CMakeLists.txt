cmake_minimum_required(VERSION 3.15)
project(mymodule LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

include(FetchContent)

FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG v2.13.6
)

FetchContent_MakeAvailable(pybind11)

pybind11_add_module(pipe_module
    src/Bindings.cpp
    src/ClientNamedPipe
    src/ServerNamedPipe
    src/PipeException
)
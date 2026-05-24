cmake_minimum_required(VERSION 3.16)
project(spectral_analyzer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O2 -Wall -Wextra")

add_executable(spectral_analyzer
    src/main.cpp
    src/csv_reader.cpp
    src/fft.cpp
    src/window.cpp
    src/welch.cpp
    src/peak_detect.cpp
    src/statistics.cpp
    src/json_writer.cpp
)

target_link_libraries(spectral_analyzer m)

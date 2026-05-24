#ifndef JSON_UTILS_HPP
#define JSON_UTILS_HPP

#include <fstream>
#include <string>
#include <sstream>

// Read entire file contents into a string.
inline std::string read_file(const std::string& path) {
    std::ifstream ifs(path);
    if (!ifs.is_open()) return "";
    std::ostringstream ss;
    ss << ifs.rdbuf();
    return ss.str();
}

#endif

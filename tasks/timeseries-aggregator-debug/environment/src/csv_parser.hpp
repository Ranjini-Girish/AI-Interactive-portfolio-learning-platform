#pragma once
#include "types.hpp"
#include <string>
#include <vector>

std::vector<SensorReading> parse_csv_file(const std::string& filepath);
time_t parse_iso_timestamp(const std::string& ts);
std::string format_iso_timestamp(time_t epoch);

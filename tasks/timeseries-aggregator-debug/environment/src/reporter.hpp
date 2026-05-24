#pragma once
#include "types.hpp"
#include <string>
#include <vector>

std::string generate_report(
    const std::vector<SensorSummary>& summaries,
    int total_records,
    int filtered_records,
    const std::string& time_start,
    const std::string& time_end,
    const std::string& config_hash,
    int precision);

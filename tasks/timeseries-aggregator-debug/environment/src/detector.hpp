#pragma once
#include "types.hpp"
#include <string>
#include <vector>

std::vector<Violation> detect_violations(
    const std::string& sensor_id,
    const std::vector<BucketStats>& buckets,
    const std::vector<ThresholdRule>& rules);

bool matches_pattern(const std::string& sensor_id, const std::string& pattern);

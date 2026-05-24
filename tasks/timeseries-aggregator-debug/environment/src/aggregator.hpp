#pragma once
#include "types.hpp"
#include <map>
#include <string>
#include <vector>

std::map<std::string, std::vector<SensorReading>> group_by_sensor(
    const std::vector<SensorReading>& readings);

std::vector<BucketStats> compute_buckets(
    const std::vector<SensorReading>& readings,
    int bucket_size_seconds);

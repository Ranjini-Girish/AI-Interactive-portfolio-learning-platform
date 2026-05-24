#include "aggregator.hpp"
#include "utils.hpp"
#include <algorithm>
#include <cmath>
#include <limits>

std::map<std::string, std::vector<SensorReading>> group_by_sensor(
    const std::vector<SensorReading>& readings) {
    std::map<std::string, std::vector<SensorReading>> groups;
    for (const auto& r : readings) {
        groups[r.sensor_id].push_back(r);
    }
    return groups;
}

std::vector<BucketStats> compute_buckets(
    const std::vector<SensorReading>& readings,
    int bucket_size_seconds) {

    if (readings.empty()) return {};

    time_t min_epoch = readings[0].epoch;
    time_t max_epoch = readings[0].epoch;
    for (const auto& r : readings) {
        min_epoch = std::min(min_epoch, r.epoch);
        max_epoch = std::max(max_epoch, r.epoch);
    }

    time_t first_bucket = (min_epoch / bucket_size_seconds) * bucket_size_seconds;
    time_t last_bucket = (max_epoch / bucket_size_seconds) * bucket_size_seconds;

    std::vector<BucketStats> buckets;

    for (time_t bs = first_bucket; bs <= last_bucket; bs += bucket_size_seconds) {
        time_t be = bs + bucket_size_seconds;

        std::vector<double> values;
        for (const auto& r : readings) {
            if (r.epoch >= bs && r.epoch <= be) {
                values.push_back(r.reading);
            }
        }

        if (values.empty()) continue;

        BucketStats stats;
        stats.bucket_start = bs;
        stats.bucket_end = be;
        stats.count = static_cast<int>(values.size());

        double sum = 0;
        stats.min_val = std::numeric_limits<double>::max();
        stats.max_val = std::numeric_limits<double>::lowest();

        for (double v : values) {
            sum += v;
            stats.min_val = std::min(stats.min_val, v);
            stats.max_val = std::max(stats.max_val, v);
        }

        stats.mean = sum / stats.count;
        stats.stddev = sample_stddev(values);

        buckets.push_back(stats);
    }

    return buckets;
}

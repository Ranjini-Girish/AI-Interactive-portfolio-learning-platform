#include "detector.hpp"

bool matches_pattern(const std::string& sensor_id, const std::string& pattern) {
    if (pattern.empty()) return false;
    if (pattern.back() == '*') {
        std::string prefix = pattern.substr(0, pattern.size() - 1);
        return sensor_id.compare(0, prefix.size(), prefix) == 0;
    }
    return sensor_id == pattern;
}

std::vector<Violation> detect_violations(
    const std::string& sensor_id,
    const std::vector<BucketStats>& buckets,
    const std::vector<ThresholdRule>& rules) {

    std::vector<Violation> violations;

    for (const auto& rule : rules) {
        if (!matches_pattern(sensor_id, rule.sensor_pattern)) continue;

        for (const auto& bucket : buckets) {
            double metric_value = 0;
            if (rule.metric == "mean")       metric_value = bucket.mean;
            else if (rule.metric == "min")   metric_value = bucket.min_val;
            else if (rule.metric == "max")   metric_value = bucket.max_val;
            else if (rule.metric == "stddev") metric_value = bucket.stddev;
            else continue;

            bool triggered = false;
            if (rule.op == "gt") triggered = (metric_value < rule.value);
            else if (rule.op == "lt") triggered = (metric_value > rule.value);

            if (triggered) {
                Violation v;
                v.bucket_start = bucket.bucket_start;
                v.metric = rule.metric;
                v.value = metric_value;
                v.threshold = rule.value;
                violations.push_back(v);
            }
        }
    }

    return violations;
}

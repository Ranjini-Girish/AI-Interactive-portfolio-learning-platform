#pragma once
#include <string>
#include <vector>
#include <ctime>

struct SensorReading {
    std::string timestamp;
    time_t epoch;
    std::string sensor_id;
    double reading;
    std::string unit;
    std::string quality;
};

struct BucketStats {
    time_t bucket_start;
    time_t bucket_end;
    double mean;
    double min_val;
    double max_val;
    double stddev;
    int count;
};

struct Violation {
    time_t bucket_start;
    std::string metric;
    double value;
    double threshold;
};

struct SensorSummary {
    std::string sensor_id;
    int record_count;
    std::vector<BucketStats> buckets;
    std::vector<Violation> violations;
};

struct ThresholdRule {
    std::string sensor_pattern;
    std::string metric;
    std::string op;
    double value;
};

struct PipelineConfig {
    int bucket_size_seconds;
    std::vector<std::string> quality_filter;
    std::vector<ThresholdRule> threshold_rules;
    int output_precision;
    std::string sort_by;
    std::string sort_order;
};

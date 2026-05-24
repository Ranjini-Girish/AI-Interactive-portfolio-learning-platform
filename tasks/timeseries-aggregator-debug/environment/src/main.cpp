#include <iostream>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <filesystem>
#include <vector>
#include "types.hpp"
#include "csv_parser.hpp"
#include "json_parser.hpp"
#include "aggregator.hpp"
#include "detector.hpp"
#include "reporter.hpp"
#include "utils.hpp"

namespace fs = std::filesystem;

static PipelineConfig load_config(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open config: " + path);
    }
    std::string content((std::istreambuf_iterator<char>(file)),
                         std::istreambuf_iterator<char>());

    JsonValue json = parse_json(content);

    PipelineConfig config;
    config.bucket_size_seconds = json["bucket_size_seconds"].as_int();
    config.output_precision = json["output_precision"].as_int();
    config.sort_by = json["sort_by"].as_string();
    config.sort_order = json["sort_order"].as_string();

    for (const auto& q : json["quality_filter"].as_array()) {
        config.quality_filter.push_back(q.as_string());
    }

    for (const auto& r : json["threshold_rules"].as_array()) {
        ThresholdRule rule;
        rule.sensor_pattern = r["sensor_pattern"].as_string();
        rule.metric = r["metric"].as_string();
        rule.op = r["operator"].as_string();
        rule.value = r["value"].as_number();
        config.threshold_rules.push_back(rule);
    }

    return config;
}

int main() {
    try {
        PipelineConfig config = load_config("/app/config/pipeline.json");

        std::vector<std::string> csv_files;
        for (const auto& entry : fs::directory_iterator("/app/data")) {
            if (entry.path().extension() == ".csv") {
                csv_files.push_back(entry.path().string());
            }
        }
        std::sort(csv_files.begin(), csv_files.end());

        std::vector<SensorReading> all_readings;
        int total_records = 0;

        for (const auto& csv_path : csv_files) {
            auto readings = parse_csv_file(csv_path);
            total_records += static_cast<int>(readings.size());

            for (const auto& r : readings) {
                bool pass = false;
                for (const auto& q : config.quality_filter) {
                    if (r.quality == q) { pass = true; break; }
                }
                if (pass) all_readings.push_back(r);
            }
        }

        int filtered_records = static_cast<int>(all_readings.size());

        if (all_readings.empty()) {
            throw std::runtime_error("No readings after filtering");
        }

        time_t min_time = all_readings[0].epoch;
        time_t max_time = all_readings[0].epoch;
        for (const auto& r : all_readings) {
            min_time = std::min(min_time, r.epoch);
            max_time = std::max(max_time, r.epoch);
        }

        auto groups = group_by_sensor(all_readings);
        std::vector<SensorSummary> summaries;

        for (const auto& [sensor_id, readings] : groups) {
            SensorSummary summary;
            summary.sensor_id = sensor_id;
            summary.record_count = static_cast<int>(readings.size());
            summary.buckets = compute_buckets(readings, config.bucket_size_seconds);
            summary.violations = detect_violations(
                sensor_id, summary.buckets, config.threshold_rules);
            summaries.push_back(summary);
        }

        std::sort(summaries.begin(), summaries.end(),
            [](const SensorSummary& a, const SensorSummary& b) {
                return a.sensor_id > b.sensor_id;
            });

        std::ifstream cf("/app/config/pipeline.json");
        std::string config_content((std::istreambuf_iterator<char>(cf)),
                                    std::istreambuf_iterator<char>());
        std::string config_hash = sha256_hex(config_content);

        std::string report = generate_report(
            summaries, total_records, filtered_records,
            format_iso_timestamp(min_time),
            format_iso_timestamp(max_time),
            config_hash, config.output_precision);

        fs::create_directories("/app/output");
        std::ofstream out("/app/output/report.json");
        out << report;
        out.close();

        std::cout << "Report written to /app/output/report.json" << std::endl;
        std::cout << "Processed " << total_records << " total records, "
                  << filtered_records << " after filtering" << std::endl;

    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}

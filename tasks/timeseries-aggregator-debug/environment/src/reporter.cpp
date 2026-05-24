#include "reporter.hpp"
#include "csv_parser.hpp"
#include "utils.hpp"
#include <sstream>
#include <iomanip>

static std::string format_double(double value, int precision) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(6) << value;
    return oss.str();
}

static std::string escape_json(const std::string& s) {
    std::string result;
    for (char c : s) {
        if (c == '"') result += "\\\"";
        else if (c == '\\') result += "\\\\";
        else if (c == '\n') result += "\\n";
        else if (c == '\t') result += "\\t";
        else result += c;
    }
    return result;
}

static std::string serialize_summaries(
    const std::vector<SensorSummary>& summaries, int precision) {

    std::ostringstream ss;
    ss << "[\n";

    for (size_t si = 0; si < summaries.size(); si++) {
        const auto& s = summaries[si];
        ss << "    {\n";
        ss << "      \"sensor_id\": \"" << escape_json(s.sensor_id) << "\",\n";
        ss << "      \"record_count\": " << s.record_count << ",\n";

        ss << "      \"buckets\": [\n";
        for (size_t bi = 0; bi < s.buckets.size(); bi++) {
            const auto& b = s.buckets[bi];
            ss << "        {\n";
            ss << "          \"start\": \"" << format_iso_timestamp(b.bucket_start) << "\",\n";
            ss << "          \"end\": \"" << format_iso_timestamp(b.bucket_end) << "\",\n";
            ss << "          \"mean\": " << format_double(b.mean, precision) << ",\n";
            ss << "          \"min\": " << format_double(b.min_val, precision) << ",\n";
            ss << "          \"max\": " << format_double(b.max_val, precision) << ",\n";
            ss << "          \"stddev\": " << format_double(b.stddev, precision) << ",\n";
            ss << "          \"count\": " << b.count << "\n";
            ss << "        }";
            if (bi + 1 < s.buckets.size()) ss << ",";
            ss << "\n";
        }
        ss << "      ],\n";

        ss << "      \"violations\": [";
        if (s.violations.empty()) {
            ss << "]\n";
        } else {
            ss << "\n";
            for (size_t vi = 0; vi < s.violations.size(); vi++) {
                const auto& v = s.violations[vi];
                ss << "        {\n";
                ss << "          \"bucket_start\": \"" << format_iso_timestamp(v.bucket_start) << "\",\n";
                ss << "          \"metric\": \"" << escape_json(v.metric) << "\",\n";
                ss << "          \"value\": " << format_double(v.value, precision) << ",\n";
                ss << "          \"threshold\": " << format_double(v.threshold, precision) << "\n";
                ss << "        }";
                if (vi + 1 < s.violations.size()) ss << ",";
                ss << "\n";
            }
            ss << "      ]\n";
        }

        ss << "    }";
        if (si + 1 < summaries.size()) ss << ",";
        ss << "\n";
    }

    ss << "  ]";
    return ss.str();
}

std::string generate_report(
    const std::vector<SensorSummary>& summaries,
    int total_records,
    int filtered_records,
    const std::string& time_start,
    const std::string& time_end,
    const std::string& config_hash,
    int precision) {

    std::string summaries_json = serialize_summaries(summaries, precision);

    std::ostringstream full;
    full << "{\n";
    full << "  \"metadata\": {\n";
    full << "    \"total_records\": " << total_records << ",\n";
    full << "    \"filtered_records\": " << filtered_records << ",\n";
    full << "    \"sensors_processed\": " << summaries.size() << ",\n";
    full << "    \"time_range\": {\n";
    full << "      \"start\": \"" << time_start << "\",\n";
    full << "      \"end\": \"" << time_end << "\"\n";
    full << "    },\n";
    full << "    \"config_hash\": \"" << config_hash << "\"\n";
    full << "  },\n";
    full << "  \"sensor_summaries\": " << summaries_json << ",\n";

    std::string full_json = full.str();
    std::string summaries_only = summaries_json;
    std::string results_hash = "sha256:" + sha256_hex(full_json);

    full << "  \"integrity\": {\n";
    full << "    \"results_hash\": \"" << results_hash << "\"\n";
    full << "  }\n";
    full << "}\n";

    return full.str();
}

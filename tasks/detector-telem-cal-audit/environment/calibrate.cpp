// Detector Telemetry Calibration & Drift — starter skeleton.
//
// This is a minimal C++ skeleton you may extend, replace, or ignore.  The
// task accepts any implementation language (Python or C++ are both fine);
// the only contract is the output file at /app/detector/report.json.  The
// container ships with `nlohmann-json3-dev` and Python 3 pre-installed.
//
// To compile and run this skeleton:
//
//     make -C /app/environment build
//     /usr/local/bin/calibrate
//
// The skeleton currently writes a stub report and exits 0.  See the task
// instructions in /app/instruction.md for the full output schema.

#include <cstdio>
#include <fstream>
#include <string>
#include <nlohmann/json.hpp>

using json = nlohmann::ordered_json;

static const char* kReportPath = "/app/detector/report.json";

int main() {
    json report;
    report["schema_version"] = 1;
    report["summary"] = json::object();
    report["per_channel_calibration"]   = json::array();
    report["per_run_summary"]           = json::array();
    report["signal_assignments"]        = json::array();
    report["channel_drift_summary"]     = json::array();
    report["channel_correlation_matrix"] = json::array();
    report["quality_findings"]          = json::array();

    std::ofstream out(kReportPath);
    if (!out) {
        std::fprintf(stderr, "cannot open %s for writing\n", kReportPath);
        return 1;
    }
    out << report.dump(2) << "\n";
    std::printf("wrote %s (stub)\n", kReportPath);
    return 0;
}

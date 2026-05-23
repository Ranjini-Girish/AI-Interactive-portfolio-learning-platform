// Seismic Localization QC — starter skeleton.
//
// This is a minimal C++ skeleton. The task accepts any implementation
// language (C++ or Python); the only contract is the output JSON at
// /app/output/localization_report.json. The container ships with
// nlohmann-json3-dev and Python 3 pre-installed.
//
// Build and run:
//     make -C /app build
//     /app/bin/seismic_audit --data /app/data --out /app/output/localization_report.json
//
// See /app/docs/ for the full specification.

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <nlohmann/json.hpp>

using json = nlohmann::ordered_json;

static const char* kDefaultOut = "/app/output/localization_report.json";

int main(int argc, char** argv) {
    std::string out_path = kDefaultOut;
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::string(argv[i]) == "--out") out_path = argv[++i];
    }

    std::filesystem::create_directories(
        std::filesystem::path(out_path).parent_path());

    json report;
    report["schema_version"] = 1;
    report["summary"] = json::object();
    report["events"] = json::array();
    report["findings"] = json::array();

    std::ofstream out(out_path);
    if (!out) {
        std::fprintf(stderr, "cannot open %s for writing\n", out_path.c_str());
        return 1;
    }
    out << report.dump(2) << "\n";
    return 0;
}

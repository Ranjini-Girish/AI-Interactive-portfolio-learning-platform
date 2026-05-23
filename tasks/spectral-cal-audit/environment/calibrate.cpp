// Spectral Calibration Audit -- starter skeleton.
//
// This is a minimal C++ skeleton you may extend, replace, or ignore. The
// task accepts any C++17 implementation; the only contract is the three
// output files under /app/output/. The container ships with
// `nlohmann-json3-dev` (you do not have to use it) and Python 3.
//
// To compile and run this skeleton:
//
//     make -C /app/environment build
//     /usr/local/bin/calibrate
//
// The skeleton currently writes empty stub output files and exits 0. See
// the task instructions in /app/instruction.md for the full schema. A
// passing submission typically ships its own /app/Makefile that builds
// /app/build/calibrate.

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <sys/stat.h>

static const char* env_or(const char* key, const char* fallback) {
    const char* v = std::getenv(key);
    return (v && *v) ? v : fallback;
}

static void mkdir_p(const std::string& path) {
    ::mkdir(path.c_str(), 0755);
}

int main() {
    std::string app_root = env_or("APP_ROOT", "/app");
    std::string out_dir  = app_root + "/output";
    mkdir_p(out_dir);

    {
        std::ofstream o(out_dir + "/run_audit.json");
        o << "{}\n";
    }
    {
        std::ofstream o(out_dir + "/calibration_summary.json");
        o << "{}\n";
    }
    {
        std::ofstream o(out_dir + "/peak_table.csv");
        o << "run_id,instrument,batch,calibrant,peak_label,expected_nm,observed_nm,error_nm,peak_area\n";
    }

    std::printf("wrote stub outputs under %s (replace with real implementation)\n", out_dir.c_str());
    return 0;
}

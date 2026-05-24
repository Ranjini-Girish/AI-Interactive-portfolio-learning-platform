#include "json_writer.h"
#include <fstream>
#include <stdexcept>

// TODO: Implement JSON output writer with sorted keys
void write_report_json(const SpectralReport& report,
                       const std::string& filepath) {
    (void)report;
    (void)filepath;
    throw std::runtime_error("JSON writer not implemented");
}

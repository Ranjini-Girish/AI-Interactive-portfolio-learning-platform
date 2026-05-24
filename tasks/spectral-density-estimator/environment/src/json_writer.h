#ifndef JSON_WRITER_H
#define JSON_WRITER_H

#include "types.h"
#include <string>

// Write a SpectralReport to a JSON file with sorted keys,
// 2-space indentation, and a trailing newline.
void write_report_json(const SpectralReport& report,
                       const std::string& filepath);

#endif

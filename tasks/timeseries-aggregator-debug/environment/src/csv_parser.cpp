#include "csv_parser.hpp"
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <cstring>

time_t parse_iso_timestamp(const std::string& ts) {
    struct tm tm = {};
    int year, month, day, hour, minute, second;
    if (sscanf(ts.c_str(), "%d-%d-%dT%d:%d:%dZ",
               &year, &month, &day, &hour, &minute, &second) != 6) {
        throw std::runtime_error("Invalid timestamp: " + ts);
    }
    tm.tm_year = year - 1900;
    tm.tm_mon = month - 1;
    tm.tm_mday = day;
    tm.tm_hour = hour;
    tm.tm_min = minute;
    tm.tm_sec = second;
    tm.tm_isdst = 0;
    return timegm(&tm);
}

std::string format_iso_timestamp(time_t epoch) {
    struct tm tm;
    gmtime_r(&epoch, &tm);
    char buf[32];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02dZ",
             tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday,
             tm.tm_hour, tm.tm_min, tm.tm_sec);
    return std::string(buf);
}

std::vector<SensorReading> parse_csv_file(const std::string& filepath) {
    std::ifstream file(filepath);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open file: " + filepath);
    }

    std::vector<SensorReading> readings;
    std::string line;

    std::getline(file, line);

    while (std::getline(file, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;

        std::stringstream ss(line);
        std::string field;
        std::vector<std::string> fields;

        while (std::getline(ss, field, ',')) {
            fields.push_back(field);
        }

        if (fields.size() < 5) continue;

        SensorReading r;
        r.timestamp = fields[0];
        r.epoch = parse_iso_timestamp(fields[0]);
        r.sensor_id = fields[1];
        r.reading = std::stod(fields[2]);
        r.unit = fields[3];
        r.quality = fields[4];
        readings.push_back(r);
    }

    return readings;
}

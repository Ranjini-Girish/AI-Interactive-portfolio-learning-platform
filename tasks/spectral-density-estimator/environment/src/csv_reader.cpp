#include "csv_reader.h"
#include <fstream>
#include <sstream>
#include <stdexcept>

SignalData read_signal_csv(const std::string& filepath) {
    SignalData data;
    std::ifstream file(filepath);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open file: " + filepath);
    }

    std::string line;
    std::getline(file, line); // skip header

    while (std::getline(file, line)) {
        if (line.empty()) continue;
        std::istringstream iss(line);
        std::string time_str, amp_str;
        std::getline(iss, time_str, ',');
        std::getline(iss, amp_str, ',');
        data.time.push_back(std::stod(time_str));
        data.amplitude.push_back(std::stod(amp_str));
    }

    data.total_samples = static_cast<int>(data.amplitude.size());
    if (data.total_samples >= 2) {
        data.sample_rate = 1.0 / (data.time[1] - data.time[0]);
    }
    return data;
}

#include "utils.hpp"
#include <cmath>
#include <openssl/sha.h>
#include <sstream>
#include <iomanip>

double sample_stddev(const std::vector<double>& values) {
    if (values.size() < 2) return 0.0;

    double sum = 0;
    for (double v : values) sum += v;
    double mean = sum / static_cast<double>(values.size());

    double sum_sq_diff = 0;
    for (double v : values) {
        double diff = v - mean;
        sum_sq_diff += diff * diff;
    }

    double variance = sum_sq_diff / values.size();
    return std::sqrt(variance);
}

std::string sha256_hex(const std::string& input) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    SHA256(reinterpret_cast<const unsigned char*>(input.c_str()),
           input.size(), hash);

    std::ostringstream ss;
    for (int i = 0; i < SHA256_DIGEST_LENGTH; i++) {
        ss << std::hex << std::setfill('0') << std::setw(2)
           << static_cast<int>(hash[i]);
    }
    return ss.str();
}

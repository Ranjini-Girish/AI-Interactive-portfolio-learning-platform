#include "peak_detect.h"
#include <cmath>
#include <algorithm>
#include <stdexcept>

// TODO: Implement peak detection with parabolic interpolation
std::vector<PeakInfo> detect_peaks(const std::vector<double>& psd_db,
                                   const std::vector<double>& frequencies,
                                   double frequency_resolution,
                                   double min_height_db,
                                   double min_prominence_db) {
    (void)psd_db;
    (void)frequencies;
    (void)frequency_resolution;
    (void)min_height_db;
    (void)min_prominence_db;
    throw std::runtime_error("Peak detection not implemented");
}

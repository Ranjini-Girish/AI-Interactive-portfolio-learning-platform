#ifndef PEAK_DETECT_H
#define PEAK_DETECT_H

#include "types.h"
#include <vector>

// Detect spectral peaks in the PSD (dB scale) with parabolic interpolation.
std::vector<PeakInfo> detect_peaks(const std::vector<double>& psd_db,
                                   const std::vector<double>& frequencies,
                                   double frequency_resolution,
                                   double min_height_db,
                                   double min_prominence_db);

#endif

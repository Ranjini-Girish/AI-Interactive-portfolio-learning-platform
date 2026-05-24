#ifndef WELCH_H
#define WELCH_H

#include "types.h"
#include "window.h"
#include <vector>

struct WelchResult {
    std::vector<double> psd;         // one-sided PSD (linear scale)
    std::vector<double> frequencies;
    int num_segments;
    int fft_bins;
    double frequency_resolution;
    WindowResult window;
};

// Compute one-sided PSD estimate using Welch's method.
WelchResult welch_psd(const std::vector<double>& signal,
                      double sample_rate,
                      int segment_length,
                      int overlap,
                      const std::string& window_type);

#endif

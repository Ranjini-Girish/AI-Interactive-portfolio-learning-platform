#include "welch.h"
#include "fft.h"
#include <cmath>
#include <stdexcept>

// TODO: Implement Welch's method for PSD estimation
WelchResult welch_psd(const std::vector<double>& signal,
                      double sample_rate,
                      int segment_length,
                      int overlap,
                      const std::string& window_type) {
    (void)signal;
    (void)sample_rate;
    (void)segment_length;
    (void)overlap;
    (void)window_type;
    throw std::runtime_error("Welch PSD not implemented");
}

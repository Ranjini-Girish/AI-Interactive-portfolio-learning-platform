#ifndef PSD_HPP
#define PSD_HPP

#include <vector>

struct PsdResult {
    std::vector<double> freqs;       // frequency bins (Hz)
    std::vector<double> psd_linear;  // one-sided PSD (linear)
    std::vector<double> psd_db;      // one-sided PSD (dB)
};

// Compute one-sided PSD from samples with given window, sample rate.
PsdResult compute_psd(const std::vector<double>& samples,
                      const std::vector<double>& window,
                      double fs);

// Welch method: average PSD over overlapping segments.
struct WelchResult {
    PsdResult psd;
    int num_segments;
    int hop_size;
    int overlap_samples;
};

WelchResult compute_welch(const std::vector<double>& samples,
                          const std::string& window_name,
                          double fs,
                          int segment_length,
                          double overlap_fraction);

#endif

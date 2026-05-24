#ifndef WINDOW_HPP
#define WINDOW_HPP

#include <string>
#include <vector>

// Generate a window function of length N.
// Supported names: "rectangular", "hann", "hamming", "blackman"
std::vector<double> make_window(const std::string& name, int N);

// Window normalization properties.
struct WindowProps {
    double S1;             // sum of window values
    double S2;             // sum of squared window values
    double coherent_gain;  // S1 / N
    double enbw_bins;      // N * S2 / S1^2
    double enbw_hz;        // enbw_bins * fs / N
};

WindowProps compute_window_props(const std::vector<double>& w, double fs);

#endif

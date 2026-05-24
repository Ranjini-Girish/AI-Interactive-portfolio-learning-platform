#ifndef WINDOW_H
#define WINDOW_H

#include <string>
#include <vector>

struct WindowResult {
    std::vector<double> coefficients;
    double s1;  // sum of window values
    double s2;  // sum of squared window values
};

// Generate the named window function of given length.
// Supported: "hann_symmetric"
WindowResult generate_window(const std::string& window_type, int length);

#endif

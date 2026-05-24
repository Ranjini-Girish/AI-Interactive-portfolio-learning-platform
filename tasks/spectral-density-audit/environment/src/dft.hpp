#ifndef DFT_HPP
#define DFT_HPP

#include "complex.hpp"
#include <vector>

// Compute the Discrete Fourier Transform of a real-valued sequence.
// Returns N complex values X[0], X[1], ..., X[N-1].
std::vector<Complex> compute_dft(const std::vector<double>& x);

#endif

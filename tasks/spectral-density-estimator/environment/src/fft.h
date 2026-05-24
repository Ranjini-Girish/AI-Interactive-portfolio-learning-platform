#ifndef FFT_H
#define FFT_H

#include <complex>
#include <vector>

// Radix-2 Cooley-Tukey FFT (in-place, decimation-in-time).
// Input length MUST be a power of 2.
void fft(std::vector<std::complex<double>>& x);

#endif

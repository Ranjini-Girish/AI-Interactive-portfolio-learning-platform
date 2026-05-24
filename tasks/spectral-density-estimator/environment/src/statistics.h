#ifndef STATISTICS_H
#define STATISTICS_H

#include "types.h"
#include <vector>

// Compute spectral statistics from the one-sided linear PSD.
SpectralStatistics compute_statistics(const std::vector<double>& psd_linear,
                                      const std::vector<double>& frequencies,
                                      double sample_rate,
                                      double s1,
                                      double s2);

#endif

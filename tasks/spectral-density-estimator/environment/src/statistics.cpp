#include "statistics.h"
#include <cmath>
#include <stdexcept>

// TODO: Implement spectral statistics computation
SpectralStatistics compute_statistics(const std::vector<double>& psd_linear,
                                      const std::vector<double>& frequencies,
                                      double sample_rate,
                                      double s1,
                                      double s2) {
    (void)psd_linear;
    (void)frequencies;
    (void)sample_rate;
    (void)s1;
    (void)s2;
    throw std::runtime_error("Statistics not implemented");
}

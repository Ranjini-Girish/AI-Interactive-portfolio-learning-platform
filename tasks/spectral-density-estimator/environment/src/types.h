#ifndef TYPES_H
#define TYPES_H

#include <complex>
#include <string>
#include <vector>

struct SignalData {
    std::vector<double> time;
    std::vector<double> amplitude;
    double sample_rate;
    int total_samples;
};

struct AnalysisConfig {
    int segment_length;
    int overlap_samples;
    std::string window_type;
    double min_peak_height_db;
    double min_peak_prominence_db;
    std::string input_file;
    std::string output_file;
};

struct PeakInfo {
    int bin_index;
    double frequency_hz;
    double power_db;
    double prominence_db;
};

struct WindowProperties {
    double s1_sum;
    double s2_sum_sq;
    double enbw_hz;
    double enbw_bins;
};

struct SpectralStatistics {
    double enbw_hz;
    double total_power;
    double spectral_flatness;
    double spectral_centroid_hz;
};

struct SpectralReport {
    double sample_rate_hz;
    int total_samples;
    double duration_s;
    int segment_length;
    int overlap_samples;
    int hop_size;
    int num_segments;
    std::string window_type;
    int fft_bins;
    double frequency_resolution_hz;
    WindowProperties window_props;
    std::vector<double> frequencies_hz;
    std::vector<double> power_density;
    std::vector<double> power_density_db;
    std::vector<PeakInfo> peaks;
    SpectralStatistics stats;
};

#endif

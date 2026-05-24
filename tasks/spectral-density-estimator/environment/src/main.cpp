#include "types.h"
#include "csv_reader.h"
#include "window.h"
#include "welch.h"
#include "peak_detect.h"
#include "statistics.h"
#include "json_writer.h"
#include <fstream>
#include <iostream>
#include <string>

static AnalysisConfig load_config(const std::string& config_path,
                                  const std::string& peak_path) {
    // TODO: Parse JSON config files
    (void)config_path;
    (void)peak_path;
    AnalysisConfig cfg;
    cfg.segment_length = 512;
    cfg.overlap_samples = 256;
    cfg.window_type = "hann_symmetric";
    cfg.min_peak_height_db = -20.0;
    cfg.min_peak_prominence_db = 5.0;
    cfg.input_file = "/app/data/sensor_timeseries.csv";
    cfg.output_file = "/app/output/spectral_report.json";
    return cfg;
}

int main() {
    try {
        auto cfg = load_config("/app/config/analysis_params.json",
                               "/app/config/peak_detection.json");

        auto signal = read_signal_csv(cfg.input_file);
        std::cout << "Loaded " << signal.total_samples << " samples at "
                  << signal.sample_rate << " Hz\n";

        auto welch = welch_psd(signal.amplitude, signal.sample_rate,
                               cfg.segment_length, cfg.overlap_samples,
                               cfg.window_type);

        std::vector<double> psd_db(welch.psd.size());
        for (size_t i = 0; i < welch.psd.size(); ++i) {
            double val = welch.psd[i] > 1e-30 ? welch.psd[i] : 1e-30;
            psd_db[i] = 10.0 * std::log10(val);
        }

        auto peaks = detect_peaks(psd_db, welch.frequencies,
                                  welch.frequency_resolution,
                                  cfg.min_peak_height_db,
                                  cfg.min_peak_prominence_db);

        auto stats = compute_statistics(welch.psd, welch.frequencies,
                                        signal.sample_rate,
                                        welch.window.s1, welch.window.s2);

        SpectralReport report;
        report.sample_rate_hz = signal.sample_rate;
        report.total_samples = signal.total_samples;
        report.duration_s = signal.total_samples / signal.sample_rate;
        report.segment_length = cfg.segment_length;
        report.overlap_samples = cfg.overlap_samples;
        report.hop_size = cfg.segment_length - cfg.overlap_samples;
        report.num_segments = welch.num_segments;
        report.window_type = cfg.window_type;
        report.fft_bins = welch.fft_bins;
        report.frequency_resolution_hz = welch.frequency_resolution;
        report.window_props.s1_sum = welch.window.s1;
        report.window_props.s2_sum_sq = welch.window.s2;
        report.window_props.enbw_hz = stats.enbw_hz;
        report.window_props.enbw_bins = stats.enbw_hz / welch.frequency_resolution;
        report.frequencies_hz = welch.frequencies;
        report.power_density = welch.psd;
        report.power_density_db = psd_db;
        report.peaks = peaks;
        report.stats = stats;

        write_report_json(report, cfg.output_file);
        std::cout << "Report written to " << cfg.output_file << "\n";

    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
    return 0;
}

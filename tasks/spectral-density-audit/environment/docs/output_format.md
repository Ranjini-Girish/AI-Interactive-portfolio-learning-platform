# Output Format

The output file `/app/output/spectral_report.json` uses 2-space indentation and a trailing newline.

## Top-Level Structure

- schema_version: integer, always 1
- total_signals_analyzed: integer count of processed signals
- analysis_config: object echoing default_window and peak_detection settings
- signals: array of per-signal analysis results, ordered by signal_id
- summary: object with aggregate counts

## Per-Signal Result

Each entry in the signals array contains:

- signal_id, sample_rate_hz, num_samples
- analysis_method: "periodogram" or "welch"
- window: name of applied window function
- window_properties: object with coherent_gain, S1, S2, enbw_bins, enbw_hz
- frequency_resolution_hz
- num_frequency_bins
- welch_parameters (only if analysis_method is "welch"): segment_length, overlap_fraction, overlap_samples, hop_size, num_segments
- spectrum: array of objects with bin, frequency_hz, psd_db for each frequency bin
- peaks: array of detected peaks with bin, frequency_hz, power_db, prominence_db
- num_peaks: integer count
- snr_db: float or null

## Summary

- total_peaks_detected: sum of num_peaks across all signals
- signals_with_peaks: count of signals where num_peaks > 0
- signals_without_peaks: count where num_peaks == 0
- welch_analyses: count using Welch method
- periodogram_analyses: count using standard periodogram

## Precision

Numerical values are rounded according to the output_precision section of config.json:
- Frequencies: frequency_decimals
- Power in dB: power_db_decimals
- SNR in dB: snr_db_decimals
- Window properties: 6 decimal places

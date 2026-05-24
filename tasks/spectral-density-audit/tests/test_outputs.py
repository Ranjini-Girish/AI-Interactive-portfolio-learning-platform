"""Tests for spectral-density-audit-hard."""
import json
import math
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

FLOAT_TOL = 1e-4
DB_TOL = 0.01
FREQ_TOL = 0.001


def load_report():
    """Load and return the main output JSON report."""
    p = OUT_DIR / "spectral_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


def sig(signal_id):
    """Return the analysis result for a given signal_id."""
    for s in R["signals"]:
        if s["signal_id"] == signal_id:
            return s
    pytest.fail(f"Signal {signal_id} not found in report")


# ═══════════════════════════════════════════════════════════════════════
# Section 1: Output File & Top-Level Structure
# ═══════════════════════════════════════════════════════════════════════


def test_output_file_exists():
    """Verify spectral_report.json was created."""
    assert (OUT_DIR / "spectral_report.json").is_file()


def test_schema_version():
    """Verify schema_version is 1."""
    assert R["schema_version"] == 1


def test_top_level_keys():
    """Verify all required top-level keys are present."""
    required = {"schema_version", "total_signals_analyzed", "analysis_config",
                "signals", "summary"}
    assert required.issubset(set(R.keys()))


def test_total_signals_analyzed():
    """Verify all 8 signals were analyzed."""
    assert R["total_signals_analyzed"] == 8


def test_signals_is_list():
    """Verify signals is a list with correct length."""
    assert isinstance(R["signals"], list)
    assert len(R["signals"]) == 8


def test_signal_ids_complete():
    """Verify all expected signal IDs are present."""
    ids = {s["signal_id"] for s in R["signals"]}
    expected = {f"signal_{i:02d}" for i in range(1, 9)}
    assert ids == expected


# ═══════════════════════════════════════════════════════════════════════
# Section 2: Per-Signal Structure Validation
# ═══════════════════════════════════════════════════════════════════════


def test_signal_required_keys():
    """Verify each signal result has all required fields."""
    required = {"signal_id", "sample_rate_hz", "num_samples", "analysis_method",
                "window", "window_properties", "frequency_resolution_hz",
                "num_frequency_bins", "spectrum", "peaks", "num_peaks", "snr_db"}
    for s in R["signals"]:
        missing = required - set(s.keys())
        assert not missing, f"{s['signal_id']} missing keys: {missing}"


def test_window_properties_keys():
    """Verify window_properties contains required sub-fields."""
    required = {"coherent_gain", "S1", "S2", "enbw_bins", "enbw_hz"}
    for s in R["signals"]:
        wp = s["window_properties"]
        missing = required - set(wp.keys())
        assert not missing, f"{s['signal_id']} window missing: {missing}"


def test_spectrum_entry_keys():
    """Verify each spectrum entry has bin, frequency_hz, psd_db."""
    for s in R["signals"]:
        for entry in s["spectrum"]:
            assert "bin" in entry and "frequency_hz" in entry and "psd_db" in entry


def test_peak_entry_keys():
    """Verify each peak entry has required fields."""
    required = {"bin", "frequency_hz", "power_db", "prominence_db"}
    for s in R["signals"]:
        for p in s["peaks"]:
            missing = required - set(p.keys())
            assert not missing, f"{s['signal_id']} peak missing: {missing}"


# ═══════════════════════════════════════════════════════════════════════
# Section 3: Window Function Assignments
# ═══════════════════════════════════════════════════════════════════════


def test_signal_01_window_rectangular():
    """Verify signal_01 uses rectangular window."""
    assert sig("signal_01")["window"] == "rectangular"


def test_signal_02_window_hann():
    """Verify signal_02 uses Hann window."""
    assert sig("signal_02")["window"] == "hann"


def test_signal_03_window_hamming():
    """Verify signal_03 uses Hamming window."""
    assert sig("signal_03")["window"] == "hamming"


def test_signal_07_window_blackman():
    """Verify signal_07 uses Blackman window."""
    assert sig("signal_07")["window"] == "blackman"


# ═══════════════════════════════════════════════════════════════════════
# Section 4: Window Normalization (S2) — KEY GOTCHA
# Window PSD normalization uses S2 = sum(w[n]^2), NOT N.
# ═══════════════════════════════════════════════════════════════════════


def test_rectangular_window_s2():
    """Rectangular window: S2 = N = 64."""
    wp = sig("signal_01")["window_properties"]
    assert math.isclose(wp["S2"], 64.0, abs_tol=FLOAT_TOL)


def test_rectangular_coherent_gain():
    """Rectangular window: coherent gain = 1.0."""
    wp = sig("signal_01")["window_properties"]
    assert math.isclose(wp["coherent_gain"], 1.0, abs_tol=FLOAT_TOL)


def test_rectangular_enbw():
    """Rectangular window: ENBW = 1.0 bins."""
    wp = sig("signal_01")["window_properties"]
    assert math.isclose(wp["enbw_bins"], 1.0, abs_tol=FLOAT_TOL)


def test_hann_window_s2():
    """Hann window with N=128: S2 ≈ 47.625 (not 128)."""
    wp = sig("signal_02")["window_properties"]
    assert math.isclose(wp["S2"], 47.625, abs_tol=FLOAT_TOL)


def test_hann_coherent_gain():
    """Hann window with N=128: coherent gain ≈ 0.496."""
    wp = sig("signal_02")["window_properties"]
    assert math.isclose(wp["coherent_gain"], 0.496094, abs_tol=1e-3)


def test_hann_enbw_bins():
    """Hann window ENBW ≈ 1.5 bins (not 1.0)."""
    wp = sig("signal_02")["window_properties"]
    assert math.isclose(wp["enbw_bins"], 1.511811, abs_tol=1e-3)


def test_hamming_window_s2():
    """Hamming window with N=64: S2 ≈ 25.04 (not 64)."""
    wp = sig("signal_03")["window_properties"]
    assert math.isclose(wp["S2"], 25.0426, abs_tol=0.01)


def test_hamming_coherent_gain():
    """Hamming coherent gain ≈ 0.5328."""
    wp = sig("signal_03")["window_properties"]
    assert math.isclose(wp["coherent_gain"], 0.532812, abs_tol=1e-3)


def test_blackman_window_s2():
    """Blackman window with N=256: S2 ≈ 77.67."""
    wp = sig("signal_07")["window_properties"]
    assert math.isclose(wp["S2"], 77.673, abs_tol=0.01)


def test_blackman_enbw_bins():
    """Blackman ENBW ≈ 1.73 bins."""
    wp = sig("signal_07")["window_properties"]
    assert math.isclose(wp["enbw_bins"], 1.733529, abs_tol=1e-3)


# ═══════════════════════════════════════════════════════════════════════
# Section 5: PSD Values — One-Sided Spectrum Doubling Gotcha
# DC (k=0) and Nyquist (k=N/2) bins must NOT be doubled.
# Interior bins must be doubled (factor of 2).
# ═══════════════════════════════════════════════════════════════════════


def test_signal_01_peak_frequency():
    """signal_01: 32 Hz pure sine → peak at exactly 32 Hz."""
    s = sig("signal_01")
    assert len(s["peaks"]) == 1
    assert math.isclose(s["peaks"][0]["frequency_hz"], 32.0, abs_tol=FREQ_TOL)


def test_signal_01_peak_power():
    """signal_01 32 Hz peak power: A=2, rect window → PSD = A²N/(2fs) = 0.5 → -3.01 dB."""
    p = sig("signal_01")["peaks"][0]
    assert math.isclose(p["power_db"], -3.0103, abs_tol=DB_TOL)


def test_signal_01_dc_not_doubled():
    """signal_01 DC bin: pure sine has zero DC → PSD(0) ≈ -300 dB (no doubling)."""
    s = sig("signal_01")
    dc_entry = s["spectrum"][0]
    assert dc_entry["bin"] == 0
    assert dc_entry["psd_db"] <= -100.0


def test_signal_06_nyquist_not_doubled():
    """signal_06 Nyquist bin: cosine at fs/2 → bin N/2 must NOT be doubled.
    A=1.5, N=64, fs=256: PSD_two = |X[32]|²/(fs*S2) = 9216/16384 = 0.5625.
    One-sided at Nyquist: same 0.5625 (NO factor of 2) → -2.4988 dB."""
    s = sig("signal_06")
    nyquist_bin = s["spectrum"][-1]
    assert nyquist_bin["bin"] == 32
    expected_db = 10.0 * math.log10(0.5625)
    assert math.isclose(nyquist_bin["psd_db"], expected_db, abs_tol=DB_TOL)


def test_signal_06_peak_at_32hz():
    """signal_06: sine at 32Hz (A=0.5) is the detected peak (not Nyquist)."""
    s = sig("signal_06")
    assert len(s["peaks"]) == 1
    assert math.isclose(s["peaks"][0]["frequency_hz"], 32.0, abs_tol=FREQ_TOL)


def test_signal_06_sine_power():
    """signal_06 peak at 32 Hz: A=0.5, rect, PSD = 0.5²*64/(2*256) = 0.03125 → -15.05 dB."""
    p = sig("signal_06")["peaks"][0]
    assert math.isclose(p["power_db"], -15.0515, abs_tol=DB_TOL)


# ═══════════════════════════════════════════════════════════════════════
# Section 6: Multi-Frequency Detection
# ═══════════════════════════════════════════════════════════════════════


def test_signal_02_two_peaks():
    """signal_02: two sines at 64 Hz and 192 Hz → exactly 2 peaks."""
    assert sig("signal_02")["num_peaks"] == 2


def test_signal_02_peak_frequencies():
    """signal_02 peaks at 64 Hz and 192 Hz."""
    peaks = sig("signal_02")["peaks"]
    freqs = [p["frequency_hz"] for p in peaks]
    assert math.isclose(freqs[0], 64.0, abs_tol=FREQ_TOL)
    assert math.isclose(freqs[1], 192.0, abs_tol=FREQ_TOL)


def test_signal_02_peak_ordering():
    """signal_02 peaks sorted by frequency ascending."""
    peaks = sig("signal_02")["peaks"]
    for i in range(len(peaks) - 1):
        assert peaks[i]["frequency_hz"] <= peaks[i + 1]["frequency_hz"]


def test_signal_02_stronger_peak_has_higher_power():
    """signal_02: A=3.0 at 64 Hz is stronger than A=1.5 at 192 Hz."""
    peaks = sig("signal_02")["peaks"]
    assert peaks[0]["power_db"] > peaks[1]["power_db"]


def test_signal_07_three_peaks():
    """signal_07: three sines at 100, 200, 400 Hz → exactly 3 peaks."""
    assert sig("signal_07")["num_peaks"] == 3


def test_signal_07_peak_frequencies():
    """signal_07 peaks at 100, 200, and 400 Hz."""
    peaks = sig("signal_07")["peaks"]
    expected = [100.0, 200.0, 400.0]
    for p, e in zip(peaks, expected):
        assert math.isclose(p["frequency_hz"], e, abs_tol=FREQ_TOL)


def test_signal_07_400hz_strongest():
    """signal_07: A=3.0 at 400 Hz is strongest, A=1.0 at 200 Hz is weakest."""
    peaks = sig("signal_07")["peaks"]
    powers = {p["frequency_hz"]: p["power_db"] for p in peaks}
    assert powers[400.0] > powers[100.0] > powers[200.0]


# ═══════════════════════════════════════════════════════════════════════
# Section 7: Welch Method (signal_04) — Segment Count Gotcha
# n_segments = floor((N - L) / hop) + 1, NOT floor(N/L)
# ═══════════════════════════════════════════════════════════════════════


def test_signal_04_analysis_method():
    """signal_04 must use Welch method."""
    assert sig("signal_04")["analysis_method"] == "welch"


def test_signal_04_welch_parameters_present():
    """signal_04 must include welch_parameters section."""
    assert "welch_parameters" in sig("signal_04")


def test_signal_04_segment_count():
    """signal_04: N=512, L=128, overlap=64, hop=64 → segments = (512-128)/64 + 1 = 7."""
    wp = sig("signal_04")["welch_parameters"]
    assert wp["num_segments"] == 7


def test_signal_04_segment_length():
    """signal_04 Welch segment length is 128."""
    assert sig("signal_04")["welch_parameters"]["segment_length"] == 128


def test_signal_04_hop_size():
    """signal_04 hop size = L - overlap_samples = 128 - 64 = 64."""
    assert sig("signal_04")["welch_parameters"]["hop_size"] == 64


def test_signal_04_overlap_samples():
    """signal_04 overlap samples = floor(128 * 0.5) = 64."""
    assert sig("signal_04")["welch_parameters"]["overlap_samples"] == 64


def test_signal_04_two_peaks():
    """signal_04: two sines at 48 Hz and 120 Hz → exactly 2 peaks."""
    assert sig("signal_04")["num_peaks"] == 2


def test_signal_04_peak_frequencies():
    """signal_04 peaks at 48 Hz and 120 Hz."""
    peaks = sig("signal_04")["peaks"]
    assert math.isclose(peaks[0]["frequency_hz"], 48.0, abs_tol=FREQ_TOL)
    assert math.isclose(peaks[1]["frequency_hz"], 120.0, abs_tol=FREQ_TOL)


def test_signal_04_frequency_resolution():
    """Welch frequency resolution = fs/L = 512/128 = 4.0 Hz (not fs/N = 1.0)."""
    s = sig("signal_04")
    assert math.isclose(s["frequency_resolution_hz"], 4.0, abs_tol=FREQ_TOL)


def test_signal_04_num_frequency_bins():
    """Welch output has L/2 + 1 = 65 bins (based on segment length, not N)."""
    assert sig("signal_04")["num_frequency_bins"] == 65


def test_signal_04_peak_power_48hz():
    """signal_04 peak at 48 Hz (A=4.0): power ≈ 1.2153 dB."""
    peaks = sig("signal_04")["peaks"]
    assert math.isclose(peaks[0]["power_db"], 1.2153, abs_tol=DB_TOL)


def test_signal_04_peak_power_120hz():
    """signal_04 peak at 120 Hz (A=2.0): power ≈ -4.8049 dB."""
    peaks = sig("signal_04")["peaks"]
    assert math.isclose(peaks[1]["power_db"], -4.8049, abs_tol=DB_TOL)


# ═══════════════════════════════════════════════════════════════════════
# Section 8: DC Offset Handling (signal_03)
# ═══════════════════════════════════════════════════════════════════════


def test_signal_03_peak_at_48hz():
    """signal_03: DC=3.0 + sine at 48 Hz → peak at 48 Hz, not at DC."""
    s = sig("signal_03")
    assert s["num_peaks"] == 1
    assert math.isclose(s["peaks"][0]["frequency_hz"], 48.0, abs_tol=FREQ_TOL)


def test_signal_03_hamming_psd():
    """signal_03 peak power with Hamming window ≈ -10.4271 dB."""
    p = sig("signal_03")["peaks"][0]
    assert math.isclose(p["power_db"], -10.4271, abs_tol=DB_TOL)


# ═══════════════════════════════════════════════════════════════════════
# Section 9: Edge Cases
# ═══════════════════════════════════════════════════════════════════════


def test_signal_05_short_signal():
    """signal_05: N=16 samples → 9 frequency bins."""
    s = sig("signal_05")
    assert s["num_samples"] == 16
    assert s["num_frequency_bins"] == 9


def test_signal_05_peak_at_16hz():
    """signal_05: 16 Hz sine detected correctly despite short signal."""
    s = sig("signal_05")
    assert s["num_peaks"] == 1
    assert math.isclose(s["peaks"][0]["frequency_hz"], 16.0, abs_tol=FREQ_TOL)


def test_signal_08_dc_only_no_peaks():
    """signal_08: constant DC signal → 0 detected peaks (DC bin excluded)."""
    s = sig("signal_08")
    assert s["num_peaks"] == 0


def test_signal_08_snr_null():
    """signal_08: no detected peaks → SNR is null."""
    assert sig("signal_08")["snr_db"] is None


def test_signal_08_hann_window():
    """signal_08: DC-only with Hann window (per config override)."""
    assert sig("signal_08")["window"] == "hann"


# ═══════════════════════════════════════════════════════════════════════
# Section 10: dB Conversion — 10*log10 NOT 20*log10
# ═══════════════════════════════════════════════════════════════════════


def test_db_uses_10log10_not_20log10():
    """signal_01 32 Hz: PSD=0.5 → 10*log10(0.5)=-3.01, not 20*log10(0.5)=-6.02."""
    p = sig("signal_01")["peaks"][0]
    wrong_20log10 = 20.0 * math.log10(0.5)
    correct_10log10 = 10.0 * math.log10(0.5)
    assert math.isclose(p["power_db"], correct_10log10, abs_tol=DB_TOL)
    assert not math.isclose(p["power_db"], wrong_20log10, abs_tol=DB_TOL)


# ═══════════════════════════════════════════════════════════════════════
# Section 11: SNR Computation
# ═══════════════════════════════════════════════════════════════════════


def test_signal_01_snr():
    """signal_01: pure sine with rectangular window → very high SNR."""
    snr = sig("signal_01")["snr_db"]
    assert snr is not None
    assert snr > 200.0


def test_signal_02_snr():
    """signal_02: two sines with Hann window → SNR ≈ 20.9 dB."""
    snr = sig("signal_02")["snr_db"]
    assert snr is not None
    assert math.isclose(snr, 20.9, abs_tol=0.1)


def test_signal_04_snr():
    """signal_04: Welch analysis SNR ≈ 20.9 dB."""
    snr = sig("signal_04")["snr_db"]
    assert snr is not None
    assert math.isclose(snr, 20.9, abs_tol=0.1)


def test_signal_06_snr():
    """signal_06: Nyquist power counted as noise → low SNR ≈ 2.5 dB."""
    snr = sig("signal_06")["snr_db"]
    assert snr is not None
    assert math.isclose(snr, 2.5, abs_tol=0.1)


# ═══════════════════════════════════════════════════════════════════════
# Section 12: Frequency Resolution
# ═══════════════════════════════════════════════════════════════════════


def test_signal_01_freq_resolution():
    """signal_01: fs=256, N=64 → Δf = 4.0 Hz."""
    assert math.isclose(sig("signal_01")["frequency_resolution_hz"], 4.0, abs_tol=FREQ_TOL)


def test_signal_05_freq_resolution():
    """signal_05: fs=128, N=16 → Δf = 8.0 Hz."""
    assert math.isclose(sig("signal_05")["frequency_resolution_hz"], 8.0, abs_tol=FREQ_TOL)


def test_signal_07_freq_resolution():
    """signal_07: fs=1024, N=256 → Δf = 4.0 Hz."""
    assert math.isclose(sig("signal_07")["frequency_resolution_hz"], 4.0, abs_tol=FREQ_TOL)


# ═══════════════════════════════════════════════════════════════════════
# Section 13: Spectrum Bin Count
# ═══════════════════════════════════════════════════════════════════════


def test_signal_01_bin_count():
    """signal_01: N=64 → N/2+1 = 33 one-sided bins."""
    assert sig("signal_01")["num_frequency_bins"] == 33


def test_signal_02_bin_count():
    """signal_02: N=128 → 65 one-sided bins."""
    assert sig("signal_02")["num_frequency_bins"] == 65


def test_signal_07_bin_count():
    """signal_07: N=256 → 129 one-sided bins."""
    assert sig("signal_07")["num_frequency_bins"] == 129


def test_signal_08_bin_count():
    """signal_08: N=32 → 17 one-sided bins."""
    assert sig("signal_08")["num_frequency_bins"] == 17


# ═══════════════════════════════════════════════════════════════════════
# Section 14: Summary Counts
# ═══════════════════════════════════════════════════════════════════════


def test_summary_total_peaks():
    """Verify summary total peak count matches sum across signals."""
    expected = sum(s["num_peaks"] for s in R["signals"])
    assert R["summary"]["total_peaks_detected"] == expected


def test_summary_signals_with_peaks():
    """Verify summary: 7 signals have peaks."""
    assert R["summary"]["signals_with_peaks"] == 7


def test_summary_signals_without_peaks():
    """Verify summary: 1 signal without peaks (signal_08)."""
    assert R["summary"]["signals_without_peaks"] == 1


def test_summary_welch_count():
    """Verify summary: 1 Welch analysis."""
    assert R["summary"]["welch_analyses"] == 1


def test_summary_periodogram_count():
    """Verify summary: 7 periodogram analyses."""
    assert R["summary"]["periodogram_analyses"] == 7


# ═══════════════════════════════════════════════════════════════════════
# Section 15: Cross-Signal Consistency
# ═══════════════════════════════════════════════════════════════════════


def test_num_peaks_matches_peaks_array():
    """Verify num_peaks equals len(peaks) for every signal."""
    for s in R["signals"]:
        assert s["num_peaks"] == len(s["peaks"]), (
            f"{s['signal_id']}: num_peaks={s['num_peaks']} != len={len(s['peaks'])}")


def test_spectrum_length_matches_num_bins():
    """Verify spectrum array length equals num_frequency_bins."""
    for s in R["signals"]:
        assert len(s["spectrum"]) == s["num_frequency_bins"]


def test_spectrum_bins_sequential():
    """Verify spectrum bins are 0, 1, 2, ... in order."""
    for s in R["signals"]:
        bins = [e["bin"] for e in s["spectrum"]]
        assert bins == list(range(len(bins)))


def test_spectrum_frequencies_ascending():
    """Verify spectrum frequencies are in ascending order."""
    for s in R["signals"]:
        freqs = [e["frequency_hz"] for e in s["spectrum"]]
        assert freqs == sorted(freqs)


def test_peak_bins_within_spectrum():
    """Verify all peak bins reference valid spectrum indices."""
    for s in R["signals"]:
        n_bins = s["num_frequency_bins"]
        for p in s["peaks"]:
            assert 0 <= p["bin"] < n_bins


def test_periodogram_signals_no_welch_params():
    """Verify periodogram signals do not have welch_parameters."""
    for s in R["signals"]:
        if s["analysis_method"] == "periodogram":
            assert "welch_parameters" not in s, (
                f"{s['signal_id']} is periodogram but has welch_parameters")


# ═══════════════════════════════════════════════════════════════════════
# Section 16: Gotcha-Specific Cross-Validation
# ═══════════════════════════════════════════════════════════════════════


def test_hann_s2_not_equal_n():
    """Hann S2 must differ from N (the rectangular-window trap)."""
    wp = sig("signal_02")["window_properties"]
    assert not math.isclose(wp["S2"], 128.0, abs_tol=1.0), (
        "Hann S2 must not equal N=128; it should be ~47.625")


def test_welch_segments_not_floor_n_over_l():
    """Welch segments=7, not floor(N/L)=floor(512/128)=4."""
    wp = sig("signal_04")["welch_parameters"]
    assert wp["num_segments"] != 4, "Used floor(N/L) instead of proper overlap formula"
    assert wp["num_segments"] == 7


def test_welch_freq_resolution_uses_segment_length():
    """Welch Δf = fs/L = 4.0, not fs/N = 1.0."""
    s = sig("signal_04")
    assert not math.isclose(s["frequency_resolution_hz"], 1.0, abs_tol=0.1), (
        "Welch Δf must use segment length L, not total N")


def test_signal_06_nyquist_lower_than_if_doubled():
    """Nyquist bin must NOT be doubled. If doubled, PSD would be 1.125 → 0.51 dB."""
    s = sig("signal_06")
    nyquist = s["spectrum"][-1]
    wrong_doubled_db = 10.0 * math.log10(2 * 0.5625)
    assert not math.isclose(nyquist["psd_db"], wrong_doubled_db, abs_tol=DB_TOL), (
        "Nyquist bin was incorrectly doubled")


def test_signal_01_psd_not_normalized_by_n():
    """Rectangular window: S2=N, so normalizations coincide. Verify via value.
    PSD[8] = 2*|X[8]|²/(fs*N) = 2*4096/16384 = 0.5 → -3.01 dB.
    Wrong normalization by N² would give |X[8]|²/N² = 4096/4096 = 1 → 0 dB."""
    p = sig("signal_01")["peaks"][0]
    assert not math.isclose(p["power_db"], 0.0, abs_tol=DB_TOL), (
        "PSD appears to use wrong normalization (divided by N² not fs*S2)")

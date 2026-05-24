"""Tests for the spectral density estimator output."""
import json
import math
import pathlib


ROOT = pathlib.Path("/app")


OUT_DIR = ROOT.parent / "output" if not (ROOT / "output").is_dir() else ROOT / "output"
REPORT_PATH = OUT_DIR / "spectral_report.json"


def _load_report():
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    text = REPORT_PATH.read_text(encoding="utf-8")
    return json.loads(text), text


# ── JSON structure and formatting ────────────────────────────────────────────


def test_report_file_exists():
    """Output JSON file must exist."""
    assert REPORT_PATH.exists()


def test_report_valid_json():
    """Output must be valid JSON."""
    _load_report()


def test_report_trailing_newline():
    """JSON file must end with a trailing newline."""
    text = REPORT_PATH.read_text(encoding="utf-8")
    assert text.endswith("\n"), "Missing trailing newline"


def test_report_two_space_indent():
    """JSON must use 2-space indentation."""
    text = REPORT_PATH.read_text(encoding="utf-8")
    lines = text.split("\n")
    indented = [ln for ln in lines if ln and ln[0] == " "]
    assert len(indented) > 0
    for line in indented:
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        assert indent % 2 == 0, f"Odd indentation ({indent}) in: {line[:60]}"


def test_top_level_keys():
    """Report must have exactly the expected top-level keys."""
    report, _ = _load_report()
    expected = {"metadata", "peaks", "psd", "statistics", "window_properties"}
    assert set(report.keys()) == expected


def test_sorted_keys_top_level():
    """Top-level keys must be sorted alphabetically."""
    _, text = _load_report()
    report = json.loads(text)
    keys = list(report.keys())
    assert keys == sorted(keys), f"Top-level keys not sorted: {keys}"


def test_sorted_keys_metadata():
    """Metadata keys must be sorted."""
    report, _ = _load_report()
    keys = list(report["metadata"].keys())
    assert keys == sorted(keys)


def test_sorted_keys_statistics():
    """Statistics keys must be sorted."""
    report, _ = _load_report()
    keys = list(report["statistics"].keys())
    assert keys == sorted(keys)


def test_sorted_keys_window():
    """Window properties keys must be sorted."""
    report, _ = _load_report()
    keys = list(report["window_properties"].keys())
    assert keys == sorted(keys)


def test_sorted_keys_psd():
    """PSD keys must be sorted."""
    report, _ = _load_report()
    keys = list(report["psd"].keys())
    assert keys == sorted(keys)


# ── Metadata ─────────────────────────────────────────────────────────────────


def test_sample_rate():
    """Sample rate must be 1024 Hz."""
    report, _ = _load_report()
    assert report["metadata"]["sample_rate_hz"] == 1024.0


def test_total_samples():
    """Total samples must be 4096."""
    report, _ = _load_report()
    assert report["metadata"]["total_samples"] == 4096


def test_duration():
    """Duration must be 4.0 seconds."""
    report, _ = _load_report()
    assert report["metadata"]["duration_s"] == 4.0


def test_segment_length():
    """Segment length must be 512."""
    report, _ = _load_report()
    assert report["metadata"]["segment_length"] == 512


def test_overlap():
    """Overlap must be 256 samples."""
    report, _ = _load_report()
    assert report["metadata"]["overlap_samples"] == 256


def test_hop_size():
    """Hop size must be segment_length - overlap = 256."""
    report, _ = _load_report()
    assert report["metadata"]["hop_size"] == 256


def test_num_segments():
    """Number of segments: floor((4096-512)/256) + 1 = 15."""
    report, _ = _load_report()
    assert report["metadata"]["num_segments"] == 15


def test_window_type():
    """Window type must be hann_symmetric."""
    report, _ = _load_report()
    assert report["metadata"]["window_type"] == "hann_symmetric"


def test_fft_bins():
    """FFT bins must be segment_length/2 + 1 = 257."""
    report, _ = _load_report()
    assert report["metadata"]["fft_bins"] == 257


def test_frequency_resolution():
    """Frequency resolution must be fs/segment_length = 2.0 Hz."""
    report, _ = _load_report()
    assert report["metadata"]["frequency_resolution_hz"] == 2.0


# ── Window properties ────────────────────────────────────────────────────────


def test_s1_sum():
    """S1 (sum of Hann window) must be 255.5."""
    report, _ = _load_report()
    assert abs(report["window_properties"]["s1_sum"] - 255.5) < 0.01


def test_s2_sum_sq():
    """S2 (sum of squared Hann window) must be 191.625."""
    report, _ = _load_report()
    assert abs(report["window_properties"]["s2_sum_sq"] - 191.625) < 0.01


def test_enbw_hz():
    """ENBW in Hz: fs * S2 / S1^2."""
    report, _ = _load_report()
    expected = 1024.0 * 191.625 / (255.5 ** 2)
    assert abs(report["window_properties"]["enbw_hz"] - expected) < 0.001


def test_enbw_bins():
    """ENBW in bins: ENBW_hz / df."""
    report, _ = _load_report()
    expected = (1024.0 * 191.625 / (255.5 ** 2)) / 2.0
    assert abs(report["window_properties"]["enbw_bins"] - expected) < 0.001


# ── PSD arrays ───────────────────────────────────────────────────────────────


def test_psd_frequencies_length():
    """Frequency array must have 257 entries."""
    report, _ = _load_report()
    assert len(report["psd"]["frequencies_hz"]) == 257


def test_psd_power_density_length():
    """Power density array must have 257 entries."""
    report, _ = _load_report()
    assert len(report["psd"]["power_density"]) == 257


def test_psd_db_length():
    """Power density dB array must have 257 entries."""
    report, _ = _load_report()
    assert len(report["psd"]["power_density_db"]) == 257


def test_frequency_first_bin():
    """First frequency bin is 0 Hz (DC)."""
    report, _ = _load_report()
    assert report["psd"]["frequencies_hz"][0] == 0.0


def test_frequency_last_bin():
    """Last frequency bin is Nyquist = fs/2 = 512 Hz."""
    report, _ = _load_report()
    assert report["psd"]["frequencies_hz"][-1] == 512.0


def test_frequency_spacing():
    """Frequency spacing must be uniform at 2 Hz."""
    report, _ = _load_report()
    freqs = report["psd"]["frequencies_hz"]
    for i in range(1, len(freqs)):
        assert abs(freqs[i] - freqs[i - 1] - 2.0) < 1e-6


def test_psd_all_nonnegative():
    """All linear PSD values must be non-negative."""
    report, _ = _load_report()
    for p in report["psd"]["power_density"]:
        assert p >= 0.0


def test_psd_db_conversion_uses_10log10():
    """PSD dB must use 10*log10 (not 20*log10)."""
    report, _ = _load_report()
    linear = report["psd"]["power_density"]
    db = report["psd"]["power_density_db"]
    for i in [50, 101, 175, 220]:
        if linear[i] > 1e-20:
            expected = 10.0 * math.log10(linear[i])
            assert abs(db[i] - expected) < 0.01, (
                f"bin {i}: expected 10*log10={expected:.4f}, got {db[i]:.4f} "
                f"(20*log10 would be {20*math.log10(linear[i]):.4f})"
            )


def test_psd_dc_not_doubled():
    """DC bin (k=0) must NOT be doubled in one-sided spectrum."""
    report, _ = _load_report()
    dc_power = report["psd"]["power_density"][0]
    assert dc_power < 0.10, (
        f"DC power={dc_power}; if doubled it would be ~0.166 instead of ~0.083"
    )
    assert dc_power > 0.05, f"DC power too low: {dc_power}"


def test_psd_nyquist_not_doubled():
    """Nyquist bin must NOT be doubled in one-sided spectrum."""
    report, _ = _load_report()
    nyq = report["psd"]["power_density"][-1]
    assert nyq < 1e-6, "Nyquist bin appears to be doubled"


def test_psd_peak_at_100hz():
    """PSD at bin 50 (100 Hz) should reflect the 2.0-amplitude component."""
    report, _ = _load_report()
    p50 = report["psd"]["power_density"][50]
    assert p50 > 0.1, f"Expected significant power at 100 Hz, got {p50}"


def test_psd_peak_at_203hz_vicinity():
    """PSD near 203 Hz (bins 101-102) should show the 1.2-amplitude component."""
    report, _ = _load_report()
    p101 = report["psd"]["power_density"][101]
    p102 = report["psd"]["power_density"][102]
    assert max(p101, p102) > 0.05, "Missing power near 203 Hz"


def test_psd_peak_at_350hz():
    """PSD at bin 175 (350 Hz) should reflect the 0.8-amplitude component."""
    report, _ = _load_report()
    p175 = report["psd"]["power_density"][175]
    assert p175 > 0.01, f"Expected significant power at 350 Hz, got {p175}"


def test_psd_peak_at_441hz_vicinity():
    """PSD near 441 Hz (bins 220-221) should show the 0.4-amplitude component."""
    report, _ = _load_report()
    p220 = report["psd"]["power_density"][220]
    p221 = report["psd"]["power_density"][221]
    assert max(p220, p221) > 0.001, "Missing power near 441 Hz"


# ── Peak detection ───────────────────────────────────────────────────────────


def test_peak_count():
    """Exactly 4 peaks should be detected."""
    report, _ = _load_report()
    assert len(report["peaks"]) == 4


def test_peaks_sorted_by_power_desc():
    """Peaks must be sorted by power_db descending."""
    report, _ = _load_report()
    powers = [p["power_db"] for p in report["peaks"]]
    assert powers == sorted(powers, reverse=True)


def test_peak_100hz_frequency():
    """Peak at ~100 Hz should be detected with interpolation."""
    report, _ = _load_report()
    freqs = [p["frequency_hz"] for p in report["peaks"]]
    close = [f for f in freqs if abs(f - 100.0) < 2.0]
    assert len(close) == 1, f"No peak near 100 Hz; found {freqs}"
    assert abs(close[0] - 100.0) < 0.5


def test_peak_203hz_frequency():
    """Peak at ~203 Hz (off-bin) should be recovered by interpolation."""
    report, _ = _load_report()
    freqs = [p["frequency_hz"] for p in report["peaks"]]
    close = [f for f in freqs if abs(f - 203.0) < 3.0]
    assert len(close) == 1, f"No peak near 203 Hz; found {freqs}"
    assert abs(close[0] - 203.0) < 1.0, (
        f"Interpolation should recover ~203 Hz, got {close[0]}"
    )


def test_peak_350hz_frequency():
    """Peak at ~350 Hz should be detected."""
    report, _ = _load_report()
    freqs = [p["frequency_hz"] for p in report["peaks"]]
    close = [f for f in freqs if abs(f - 350.0) < 2.0]
    assert len(close) == 1
    assert abs(close[0] - 350.0) < 0.5


def test_peak_441hz_frequency():
    """Peak at ~441 Hz (off-bin) should be recovered by interpolation."""
    report, _ = _load_report()
    freqs = [p["frequency_hz"] for p in report["peaks"]]
    close = [f for f in freqs if abs(f - 441.0) < 3.0]
    assert len(close) == 1, f"No peak near 441 Hz; found {freqs}"
    assert abs(close[0] - 441.0) < 1.0


def test_peak_100hz_is_strongest():
    """The 100 Hz peak (amplitude 2.0) should have the highest power."""
    report, _ = _load_report()
    assert abs(report["peaks"][0]["frequency_hz"] - 100.0) < 2.0


def test_peak_power_ordering():
    """Peak powers should follow the input amplitude ordering."""
    report, _ = _load_report()
    peaks = report["peaks"]
    powers = {round(p["frequency_hz"]): p["power_db"] for p in peaks}
    p100 = powers.get(100, powers.get(100.0, -999))
    p203 = powers.get(203, powers.get(203.0, -999))
    p350 = powers.get(350, powers.get(350.0, -999))
    p441 = powers.get(441, powers.get(441.0, -999))
    assert p100 > p203 > p350 > p441, (
        f"Power ordering wrong: 100Hz={p100}, 203Hz={p203}, 350Hz={p350}, 441Hz={p441}"
    )


def test_peak_has_bin_index():
    """Each peak must have a bin_index field."""
    report, _ = _load_report()
    for p in report["peaks"]:
        assert "bin_index" in p
        assert isinstance(p["bin_index"], int)


def test_peak_has_prominence():
    """Each peak must have a prominence_db field."""
    report, _ = _load_report()
    for p in report["peaks"]:
        assert "prominence_db" in p
        assert p["prominence_db"] > 0


def test_peak_100hz_power_db():
    """Power at 100 Hz peak should be approximately -1.77 dB."""
    report, _ = _load_report()
    peak = next(p for p in report["peaks"] if abs(p["frequency_hz"] - 100.0) < 2.0)
    assert abs(peak["power_db"] - (-1.769)) < 0.5


def test_peak_203hz_power_db():
    """Power at 203 Hz peak should be approximately -5.89 dB."""
    report, _ = _load_report()
    peak = next(p for p in report["peaks"] if abs(p["frequency_hz"] - 203.0) < 3.0)
    assert abs(peak["power_db"] - (-5.886)) < 0.5


def test_peak_350hz_power_db():
    """Power at 350 Hz peak should be approximately -9.73 dB."""
    report, _ = _load_report()
    peak = next(p for p in report["peaks"] if abs(p["frequency_hz"] - 350.0) < 2.0)
    assert abs(peak["power_db"] - (-9.728)) < 0.5


def test_peak_441hz_power_db():
    """Power at 441 Hz peak should be approximately -15.43 dB."""
    report, _ = _load_report()
    peak = next(p for p in report["peaks"] if abs(p["frequency_hz"] - 441.0) < 3.0)
    assert abs(peak["power_db"] - (-15.428)) < 0.5


# ── Statistics ───────────────────────────────────────────────────────────────


def test_enbw_statistic():
    """ENBW in statistics must match window_properties."""
    report, _ = _load_report()
    assert abs(
        report["statistics"]["enbw_hz"] - report["window_properties"]["enbw_hz"]
    ) < 1e-6


def test_total_power():
    """Total power (integral of PSD) should be ~3.37."""
    report, _ = _load_report()
    tp = report["statistics"]["total_power"]
    assert abs(tp - 3.37) < 0.1, f"Total power {tp} differs from expected ~3.37"


def test_total_power_matches_parseval():
    """Total power should approximately equal sum of component powers."""
    report, _ = _load_report()
    tp = report["statistics"]["total_power"]
    expected = 0.5**2 + 2.0**2 / 2 + 1.2**2 / 2 + 0.8**2 / 2 + 0.4**2 / 2
    assert abs(tp - expected) < 0.15, (
        f"Total power {tp} vs Parseval estimate {expected}"
    )


def test_spectral_flatness_near_zero():
    """Spectral flatness of a tonal signal should be near zero."""
    report, _ = _load_report()
    sf = report["statistics"]["spectral_flatness"]
    assert sf < 0.01, f"Spectral flatness {sf} too high for tonal signal"


def test_spectral_centroid_range():
    """Spectral centroid must be between 0 and Nyquist."""
    report, _ = _load_report()
    sc = report["statistics"]["spectral_centroid_hz"]
    assert 0 < sc < 512.0


def test_spectral_centroid_value():
    """Spectral centroid should be approximately 146.47 Hz."""
    report, _ = _load_report()
    sc = report["statistics"]["spectral_centroid_hz"]
    assert abs(sc - 146.47) < 5.0, f"Centroid {sc} differs from expected ~146.47"


# ── Cross-consistency checks ────────────────────────────────────────────────


def test_psd_db_matches_linear():
    """PSD dB values should match 10*log10 of linear values at peak bins."""
    report, _ = _load_report()
    linear = report["psd"]["power_density"]
    db = report["psd"]["power_density_db"]
    for peak in report["peaks"]:
        k = peak["bin_index"]
        if linear[k] > 1e-20:
            expected_db = 10.0 * math.log10(linear[k])
            assert abs(db[k] - expected_db) < 0.1


def test_peak_frequencies_match_psd_freqs():
    """Peak bin_index * df should approximately match peak frequency."""
    report, _ = _load_report()
    df = report["metadata"]["frequency_resolution_hz"]
    for peak in report["peaks"]:
        base_freq = peak["bin_index"] * df
        assert abs(peak["frequency_hz"] - base_freq) < df


def test_total_power_from_psd_array():
    """Total power should equal sum(PSD) * df."""
    report, _ = _load_report()
    df = report["metadata"]["frequency_resolution_hz"]
    integral = sum(report["psd"]["power_density"]) * df
    assert abs(report["statistics"]["total_power"] - integral) < 0.01


def test_segment_count_formula():
    """Segment count must follow floor((N-L)/H)+1."""
    report, _ = _load_report()
    m = report["metadata"]
    expected = (m["total_samples"] - m["segment_length"]) // m["hop_size"] + 1
    assert m["num_segments"] == expected


def test_no_spurious_peaks_below_40hz():
    """No peaks should appear below 40 Hz (only DC offset, no sinusoids)."""
    report, _ = _load_report()
    low_peaks = [p for p in report["peaks"] if p["frequency_hz"] < 40.0]
    assert len(low_peaks) == 0, f"Spurious peaks below 40 Hz: {low_peaks}"


def test_no_peaks_above_nyquist():
    """No peaks should appear above 512 Hz."""
    report, _ = _load_report()
    bad = [p for p in report["peaks"] if p["frequency_hz"] > 512.0]
    assert len(bad) == 0

"""
Oracle solution for spectral-density-audit-hard.
Computes DFT-based power spectral density with proper normalization.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

DATA_DIR = Path("/app/data")
SIGNALS_DIR = DATA_DIR / "signals"
OUT_DIR = Path("/app/output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def round_freq(x, d):
    return round(x, d)

def round_pdb(x, d):
    return round(x, d)

def round_snr(x, d):
    return round(x, d)


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ─── Window functions ────────────────────────────────────────────────────────

def window_rectangular(N):
    return [1.0] * N

def window_hann(N):
    return [0.5 * (1.0 - math.cos(2.0 * math.pi * n / (N - 1))) for n in range(N)]

def window_hamming(N):
    return [0.54 - 0.46 * math.cos(2.0 * math.pi * n / (N - 1)) for n in range(N)]

def window_blackman(N):
    return [0.42 - 0.5 * math.cos(2.0 * math.pi * n / (N - 1))
            + 0.08 * math.cos(4.0 * math.pi * n / (N - 1)) for n in range(N)]

def get_window(name, N):
    funcs = {
        "rectangular": window_rectangular,
        "hann": window_hann,
        "hamming": window_hamming,
        "blackman": window_blackman,
    }
    return funcs[name](N)


# ─── DFT (direct, no FFT library needed) ─────────────────────────────────────

def dft(x):
    """Compute DFT of real-valued sequence x. Returns list of (re, im) tuples."""
    N = len(x)
    result = []
    for k in range(N):
        re_sum = 0.0
        im_sum = 0.0
        for n in range(N):
            angle = 2.0 * math.pi * k * n / N
            re_sum += x[n] * math.cos(angle)
            im_sum -= x[n] * math.sin(angle)
        result.append((re_sum, im_sum))
    return result


# ─── PSD computation ─────────────────────────────────────────────────────────

def compute_psd_onesided(samples, window_values, fs):
    """
    Compute one-sided power spectral density.

    PSD_twosided[k] = |X[k]|^2 / (fs * S2)
    where S2 = sum(w[n]^2), X = DFT(x[n] * w[n])

    One-sided:
      PSD[0] = PSD_twosided[0]                          (DC, no doubling)
      PSD[k] = 2 * PSD_twosided[k]  for 0 < k < N/2    (doubled)
      PSD[N/2] = PSD_twosided[N/2]                      (Nyquist, no doubling)
    """
    N = len(samples)
    S2 = sum(w * w for w in window_values)

    # Apply window
    xw = [samples[n] * window_values[n] for n in range(N)]

    # DFT
    X = dft(xw)

    # Two-sided PSD
    psd_two = [0.0] * N
    for k in range(N):
        mag2 = X[k][0] ** 2 + X[k][1] ** 2
        psd_two[k] = mag2 / (fs * S2)

    # One-sided PSD: bins 0 to N/2
    n_onesided = N // 2 + 1
    psd = [0.0] * n_onesided

    psd[0] = psd_two[0]  # DC: no doubling
    for k in range(1, N // 2):
        psd[k] = 2.0 * psd_two[k]  # Interior: doubled
    psd[N // 2] = psd_two[N // 2]  # Nyquist: no doubling

    # Frequency bins
    freqs = [k * fs / N for k in range(n_onesided)]

    return freqs, psd


def compute_welch_psd(samples, window_name, fs, segment_length, overlap_fraction):
    """
    Welch's method: average PSD over overlapping segments.

    n_segments = floor((N - segment_length) / hop) + 1
    where hop = segment_length - overlap_samples
    """
    N = len(samples)
    L = segment_length
    overlap_samples = int(math.floor(L * overlap_fraction))
    hop = L - overlap_samples

    n_segments = (N - L) // hop + 1

    window_values = get_window(window_name, L)
    n_onesided = L // 2 + 1

    # Accumulate PSD
    psd_accum = [0.0] * n_onesided

    for seg_idx in range(n_segments):
        start = seg_idx * hop
        segment = samples[start:start + L]
        freqs, psd_seg = compute_psd_onesided(segment, window_values, fs)
        for k in range(n_onesided):
            psd_accum[k] += psd_seg[k]

    # Average
    psd_avg = [p / n_segments for p in psd_accum]
    freqs = [k * fs / L for k in range(n_onesided)]

    return freqs, psd_avg, n_segments


# ─── Peak detection with prominence ──────────────────────────────────────────

def psd_to_db(psd_val):
    """Convert linear PSD to dB. Use 10*log10 (power quantity)."""
    if psd_val <= 0:
        return -300.0
    return 10.0 * math.log10(psd_val)


def detect_peaks(psd_db, freqs, min_height_db, prominence_threshold_db):
    """
    Detect peaks in PSD (dB).
    A peak at bin k requires:
      1. psd_db[k] > psd_db[k-1] AND psd_db[k] > psd_db[k+1]
      2. psd_db[k] >= min_height_db
      3. prominence >= prominence_threshold_db

    Prominence: scan left from peak until a bin >= peak is found, record
    the minimum encountered. Do the same scanning right. Prominence =
    peak_height - max(left_min, right_min).
    """
    n = len(psd_db)
    peaks = []

    for k in range(1, n - 1):
        if psd_db[k] <= psd_db[k - 1] or psd_db[k] <= psd_db[k + 1]:
            continue
        if psd_db[k] < min_height_db:
            continue

        # Compute prominence
        # Scan left
        left_min = psd_db[k]
        for j in range(k - 1, -1, -1):
            left_min = min(left_min, psd_db[j])
            if psd_db[j] >= psd_db[k]:
                break

        # Scan right
        right_min = psd_db[k]
        for j in range(k + 1, n):
            right_min = min(right_min, psd_db[j])
            if psd_db[j] >= psd_db[k]:
                break

        prominence = psd_db[k] - max(left_min, right_min)
        if prominence >= prominence_threshold_db:
            peaks.append(PeakInfo(k, freqs[k], psd_db[k], prominence))

    return peaks


class PeakInfo:
    def __init__(self, bin_idx, freq, power_db, prominence):
        self.bin = bin_idx
        self.frequency_hz = freq
        self.power_db = power_db
        self.prominence_db = prominence


# ─── SNR computation ──────────────────────────────────────────────────────────

def compute_snr(psd_linear, peak_bins):
    """
    SNR = 10 * log10(signal_power / noise_power)
    signal_power = sum of PSD at peak bins (linear)
    noise_power = mean of PSD at non-peak bins (linear)
    """
    peak_set = set(peak_bins)
    signal_power = sum(psd_linear[k] for k in peak_set)
    if signal_power <= 0:
        return None
    noise_bins = [psd_linear[k] for k in range(len(psd_linear)) if k not in peak_set]
    if not noise_bins or all(v <= 0 for v in noise_bins):
        return None  # Infinite or undefined SNR
    noise_power = sum(noise_bins) / len(noise_bins)
    if noise_power <= 0:
        return None
    return 10.0 * math.log10(signal_power / noise_power)


# ─── Main analysis ───────────────────────────────────────────────────────────

def analyze_signal(signal_data, config, per_signal):
    """Analyze a single signal and return its result dict."""
    sig_id = signal_data["signal_id"]
    fs = signal_data["sample_rate_hz"]
    samples = signal_data["samples"]
    N = len(samples)

    # Determine window
    window_name = per_signal.get("window", config["analysis_parameters"]["default_window"])

    # Determine Welch parameters
    welch_cfg = per_signal.get("welch", config["analysis_parameters"]["default_welch"])
    welch_enabled = welch_cfg.get("enabled", False)

    # Precision settings
    prec = config["analysis_parameters"]["output_precision"]
    fd = prec["frequency_decimals"]
    pd = prec["power_db_decimals"]
    sd = prec["snr_db_decimals"]

    # Compute PSD
    if welch_enabled:
        seg_len = welch_cfg["segment_length"]
        overlap_frac = welch_cfg["overlap_fraction"]
        freqs, psd_linear, n_segments = compute_welch_psd(
            samples, window_name, fs, seg_len, overlap_frac
        )
        analysis_method = "welch"
    else:
        window_values = get_window(window_name, N)
        freqs, psd_linear = compute_psd_onesided(samples, window_values, fs)
        n_segments = 1
        analysis_method = "periodogram"

    # Convert to dB
    psd_db = [psd_to_db(p) for p in psd_linear]

    # Peak detection
    min_h = config["analysis_parameters"]["peak_detection"]["min_height_db"]
    prom = config["analysis_parameters"]["peak_detection"]["prominence_db"]
    peaks = detect_peaks(psd_db, freqs, min_h, prom)

    # Sort peaks by frequency ascending
    peaks.sort(key=lambda p: p.frequency_hz)

    # SNR
    peak_bins = [p.bin for p in peaks]
    snr = compute_snr(psd_linear, peak_bins)

    # Window properties
    if welch_enabled:
        seg_len = welch_cfg["segment_length"]
        wvals = get_window(window_name, seg_len)
    else:
        wvals = get_window(window_name, N)
    S1 = sum(wvals)
    S2 = sum(w * w for w in wvals)
    coherent_gain = S1 / len(wvals)
    enbw = len(wvals) * S2 / (S1 * S1)  # Equivalent noise bandwidth (bins)
    enbw_hz = enbw * fs / len(wvals)

    # Build result
    freq_resolution = fs / (welch_cfg["segment_length"] if welch_enabled else N)

    result = {
        "signal_id": sig_id,
        "sample_rate_hz": fs,
        "num_samples": N,
        "analysis_method": analysis_method,
        "window": window_name,
        "window_properties": {
            "coherent_gain": round(coherent_gain, 6),
            "S1": round(S1, 6),
            "S2": round(S2, 6),
            "enbw_bins": round(enbw, 6),
            "enbw_hz": round(enbw_hz, 6),
        },
        "frequency_resolution_hz": round_freq(freq_resolution, fd),
        "num_frequency_bins": len(freqs),
    }

    if welch_enabled:
        overlap_samples = int(math.floor(
            welch_cfg["segment_length"] * welch_cfg["overlap_fraction"]
        ))
        result["welch_parameters"] = {
            "segment_length": welch_cfg["segment_length"],
            "overlap_fraction": welch_cfg["overlap_fraction"],
            "overlap_samples": overlap_samples,
            "hop_size": welch_cfg["segment_length"] - overlap_samples,
            "num_segments": n_segments,
        }

    # PSD spectrum (all bins)
    spectrum = []
    for k in range(len(freqs)):
        spectrum.append({
            "bin": k,
            "frequency_hz": round_freq(freqs[k], fd),
            "psd_db": round_pdb(psd_db[k], pd),
        })
    result["spectrum"] = spectrum

    # Detected peaks
    result["peaks"] = [
        {
            "bin": p.bin,
            "frequency_hz": round_freq(p.frequency_hz, fd),
            "power_db": round_pdb(p.power_db, pd),
            "prominence_db": round_pdb(p.prominence_db, pd),
        }
        for p in peaks
    ]
    result["num_peaks"] = len(peaks)

    # SNR
    result["snr_db"] = round_snr(snr, sd) if snr is not None else None

    return result


def main():
    # Load config
    config = json.loads((DATA_DIR / "config.json").read_text(encoding="utf-8"))
    per_signal_overrides = config.get("per_signal_overrides", {})

    # Load and analyze all signals
    signal_files = sorted(SIGNALS_DIR.glob("signal_*.json"))
    results = []

    for sf in signal_files:
        sig_data = json.loads(sf.read_text(encoding="utf-8"))
        sig_id = sig_data["signal_id"]
        overrides = per_signal_overrides.get(sig_id, {})
        result = analyze_signal(sig_data, config, overrides)
        results.append(result)

    # Build report
    report = {
        "schema_version": 1,
        "total_signals_analyzed": len(results),
        "analysis_config": {
            "default_window": config["analysis_parameters"]["default_window"],
            "peak_detection": config["analysis_parameters"]["peak_detection"],
        },
        "signals": results,
        "summary": {
            "total_peaks_detected": sum(r["num_peaks"] for r in results),
            "signals_with_peaks": sum(1 for r in results if r["num_peaks"] > 0),
            "signals_without_peaks": sum(1 for r in results if r["num_peaks"] == 0),
            "welch_analyses": sum(1 for r in results if r["analysis_method"] == "welch"),
            "periodogram_analyses": sum(1 for r in results
                                        if r["analysis_method"] == "periodogram"),
        },
    }

    write_json(OUT_DIR / "spectral_report.json", report)
    print("Spectral report written to /app/output/spectral_report.json")


main()

if __name__ == "__main__":
    raise SystemExit(0)

# Welch's Method for PSD Estimation

## Overview

Welch's method estimates the power spectral density by:

1. Dividing the signal into overlapping segments
2. Applying a window to each segment
3. Computing the FFT of each windowed segment
4. Computing the periodogram of each segment
5. Averaging the periodograms across segments

The averaging reduces the variance of the PSD estimate compared to a single
periodogram of the full signal.

## Segmentation

Given a signal of N samples, segment length L, and overlap O:

- Hop size: H = L - O
- Number of segments: K = floor((N - L) / H) + 1

Each segment k starts at index k * H and spans [k*H, k*H + L - 1].

## Periodogram Computation

For each windowed segment x_w[n]:

1. Compute X[k] = FFT(x_w)
2. Raw periodogram: P[k] = |X[k]|^2 / (fs * S2)

where S2 = sum(w[n]^2) and fs is the sample rate.

The normalization by (fs * S2) ensures the PSD has correct physical units
(power per Hz) and accounts for the energy lost due to windowing.

## One-Sided Spectrum

For real-valued signals, the negative frequencies mirror the positive ones.
The one-sided PSD doubles the two-sided PSD for all bins EXCEPT:

- DC (k = 0): NOT doubled (no mirror component)
- Nyquist (k = N_seg/2): NOT doubled (maps to itself)

All other bins k = 1, 2, ..., N_seg/2 - 1 are multiplied by 2.

## Averaging

The final PSD estimate is the arithmetic mean of all K periodograms:

    PSD[k] = (1/K) * sum(P_i[k] for i = 0..K-1)

## Peak Detection with Parabolic Interpolation

A bin k is a local maximum if PSD_dB[k] > PSD_dB[k-1] and PSD_dB[k] > PSD_dB[k+1].

For each local maximum satisfying the height and prominence thresholds,
parabolic (quadratic) interpolation refines the peak location:

    alpha = PSD_dB[k-1]
    beta  = PSD_dB[k]
    gamma = PSD_dB[k+1]

    delta = 0.5 * (alpha - gamma) / (alpha - 2*beta + gamma)

    interpolated_frequency = (k + delta) * df
    interpolated_power_db  = beta - 0.25 * (alpha - gamma) * delta

Peaks are sorted by power_db in descending order.

## Prominence

Peak prominence measures how much a peak stands out from its surroundings.
For each peak at bin k, look within a window of W bins on each side:

    left_min  = min(PSD_dB[max(0, k-W) : k])
    right_min = min(PSD_dB[k+1 : min(N, k+W+1)])
    prominence = PSD_dB[k] - max(left_min, right_min)

## Output JSON Schema

The output file must have sorted keys at every nesting level, 2-space
indentation, and a trailing newline. Structure:

```json
{
  "metadata": {
    "duration_s": ...,
    "fft_bins": ...,
    "frequency_resolution_hz": ...,
    "hop_size": ...,
    "num_segments": ...,
    "overlap_samples": ...,
    "sample_rate_hz": ...,
    "segment_length": ...,
    "total_samples": ...,
    "window_type": "hann_symmetric"
  },
  "peaks": [
    {
      "bin_index": ...,
      "frequency_hz": ...,
      "power_db": ...,
      "prominence_db": ...
    }
  ],
  "psd": {
    "frequencies_hz": [...],
    "power_density": [...],
    "power_density_db": [...]
  },
  "statistics": {
    "enbw_hz": ...,
    "spectral_centroid_hz": ...,
    "spectral_flatness": ...,
    "total_power": ...
  },
  "window_properties": {
    "enbw_bins": ...,
    "enbw_hz": ...,
    "s1_sum": ...,
    "s2_sum_sq": ...
  }
}
```

All floating-point values are rounded to 6 decimal places.

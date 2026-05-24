# Spectral Analysis Reference

## Power Spectral Density (PSD)

The power spectral density quantifies how the power of a signal is distributed
across frequency. For a discrete-time signal sampled at rate fs, the PSD has
units of power-per-hertz (V²/Hz for voltage signals).

## Windowing

Before computing the FFT of each segment, a window function is applied to
reduce spectral leakage. The choice of window affects the frequency resolution
and sidelobe levels.

### Symmetric Hann Window

The symmetric Hann window of length N is defined as:

    w[n] = 0.5 * (1 - cos(2 * pi * n / (N - 1)))    for n = 0, 1, ..., N-1

Note the divisor is (N-1), not N. This is the "symmetric" variant used in
spectral analysis. The "periodic" variant (divisor N) is used for filter
design and is NOT appropriate here.

### Window Properties

- S1 = sum(w[n])           — the DC gain of the window
- S2 = sum(w[n]^2)         — used in PSD normalization
- ENBW = fs * S2 / S1^2    — Equivalent Noise Bandwidth in Hz
- ENBW in bins = ENBW / df where df = fs / segment_length

For a symmetric Hann window of length 512:
- S1 = 255.5
- S2 = 191.625
- ENBW ≈ 3.006 Hz (at fs = 1024 Hz)

## dB Conversion

Power spectral density in decibels uses:

    PSD_dB = 10 * log10(PSD_linear)

Note: 10*log10 is correct for POWER quantities. The 20*log10 formula is only
for AMPLITUDE quantities (voltages, pressures). Since PSD is a power density,
always use 10*log10.

## Frequency Vector

For a segment of length N_seg sampled at fs:
- Frequency resolution: df = fs / N_seg
- One-sided frequency bins: f[k] = k * df for k = 0, 1, ..., N_seg/2
- Total one-sided bins: N_seg/2 + 1

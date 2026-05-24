# Window Functions

All window functions are defined for n = 0, 1, ..., N-1 where N is the window length. The cosine argument uses the symmetric form n/(N-1).

## Rectangular

w[n] = 1 for all n

Properties: S1 = N, S2 = N, coherent_gain = 1.0, ENBW = 1.0 bins.

## Hann (Hanning)

w[n] = 0.5 * (1 - cos(2π * n / (N - 1)))

The Hann window tapers to zero at both endpoints. It provides good frequency resolution with moderate sidelobe suppression.

## Hamming

w[n] = 0.54 - 0.46 * cos(2π * n / (N - 1))

The Hamming window does not taper to zero at the endpoints (minimum value ≈ 0.08). It has lower first sidelobes than Hann but higher far sidelobes.

Note the coefficients: 0.54 and 0.46 for Hamming, versus 0.5 and 0.5 for Hann.

## Blackman

w[n] = 0.42 - 0.5 * cos(2π * n / (N - 1)) + 0.08 * cos(4π * n / (N - 1))

The Blackman window has three cosine terms and provides excellent sidelobe suppression at the cost of wider main lobe.

## Window Properties

- **S1** = Σ w[n]: sum of window values
- **S2** = Σ w[n]²: sum of squared window values
- **Coherent Gain** = S1 / N: the DC gain of the window
- **ENBW (bins)** = N * S2 / S1²: equivalent noise bandwidth in frequency bins
- **ENBW (Hz)** = ENBW_bins * fs / N_window: ENBW in Hertz

The S2 normalization is critical for PSD estimation. Using N instead of S2 in the PSD denominator produces incorrect power levels for non-rectangular windows.

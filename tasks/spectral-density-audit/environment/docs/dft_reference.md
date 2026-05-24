# Discrete Fourier Transform Reference

The DFT of a length-N sequence x[n] is defined as:

X[k] = Σ_{n=0}^{N-1} x[n] * exp(-j * 2π * k * n / N)

for k = 0, 1, ..., N-1.

The inverse DFT recovers the original signal:

x[n] = (1/N) * Σ_{k=0}^{N-1} X[k] * exp(j * 2π * k * n / N)

## Frequency Mapping

Each bin k corresponds to frequency f_k = k * fs / N, where fs is the sample rate. The frequency resolution is Δf = fs / N.

For a real-valued signal, the DFT satisfies the conjugate symmetry property: X[N-k] = conj(X[k]). This means the information in bins k > N/2 is redundant. The one-sided spectrum uses bins k = 0, 1, ..., N/2 (total N/2 + 1 bins).

## Power Spectral Density

The two-sided PSD at bin k is:

PSD_two[k] = |X[k]|^2 / (fs * S2)

where S2 = Σ_{n=0}^{N-1} w[n]^2 is the sum of squared window values, and X[k] is the DFT of the windowed signal xw[n] = x[n] * w[n].

The one-sided PSD concentrates the symmetric energy:

- PSD[0] = PSD_two[0] (DC component, no doubling)
- PSD[k] = 2 * PSD_two[k] for 0 < k < N/2 (interior bins, doubled)
- PSD[N/2] = PSD_two[N/2] (Nyquist component, no doubling)

The DC and Nyquist bins are unique in that they do not have a symmetric counterpart that contributes additional energy, hence they are not doubled.

## Decibel Conversion

Power spectral density in decibels:

PSD_dB[k] = 10 * log10(PSD[k])

The factor of 10 (not 20) is used because PSD is a power quantity. The factor of 20 applies only to amplitude quantities.

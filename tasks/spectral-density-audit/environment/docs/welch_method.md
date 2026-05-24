# Welch's Method for PSD Estimation

Welch's method reduces the variance of PSD estimates by averaging over multiple overlapping segments of the signal.

## Segmentation

Given a signal of N samples, segment length L, and overlap fraction p:

1. Compute overlap in samples: overlap_samples = floor(L * p)
2. Compute hop size: hop = L - overlap_samples
3. Compute number of segments: n_segments = floor((N - L) / hop) + 1
4. Segment i starts at index: start_i = i * hop, for i = 0, 1, ..., n_segments - 1

Each segment contains samples[start_i : start_i + L].

## PSD Computation

For each segment:
1. Apply the window function (length L)
2. Compute the one-sided PSD of the windowed segment

The final Welch PSD is the arithmetic mean of per-segment PSDs:

PSD_welch[k] = (1 / n_segments) * Σ PSD_segment_i[k]

## Output Properties

- Frequency resolution: Δf = fs / L (determined by segment length, not total signal length)
- Number of output bins: L/2 + 1 (one-sided, based on segment length)
- Window properties (S1, S2, ENBW) are computed for the segment-length window

## Common Pitfalls

- The segment count formula uses (N - L) / hop + 1, not N / L
- Frequency resolution is fs / L, not fs / N
- The number of output bins is L/2 + 1, not N/2 + 1

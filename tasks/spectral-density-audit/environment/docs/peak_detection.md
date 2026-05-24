# Peak Detection Algorithm

Spectral peaks are detected in the dB-scaled one-sided PSD spectrum.

## Local Maximum Test

A bin k is a candidate peak if:

- k is an interior bin (0 < k < num_bins - 1)
- PSD_dB[k] > PSD_dB[k-1] (strictly greater than left neighbor)
- PSD_dB[k] > PSD_dB[k+1] (strictly greater than right neighbor)

Note: DC (k=0) and the last bin (k=num_bins-1) are never candidates because they lack a neighbor on one side.

## Height Threshold

A candidate peak must satisfy:

PSD_dB[k] >= min_height_db

Peaks below the configured minimum height are discarded.

## Prominence Test

Prominence measures how much a peak stands out from its surroundings:

1. Scan leftward from k-1 toward bin 0, tracking the running minimum of PSD_dB. Stop when encountering a bin with PSD_dB >= PSD_dB[k] or reaching the edge. Record the minimum found as left_min.
2. Scan rightward from k+1 toward the last bin, same procedure. Record right_min.
3. Prominence = PSD_dB[k] - max(left_min, right_min)

A peak is accepted if prominence >= prominence_threshold_db.

## Output

Accepted peaks are sorted by frequency_hz in ascending order. Each peak reports its bin index, frequency in Hz, power in dB, and prominence in dB.

## SNR Computation

Signal-to-noise ratio based on detected peaks:

- signal_power = sum of linear PSD values at detected peak bins
- noise_power = mean of linear PSD values at all non-peak bins
- SNR_dB = 10 * log10(signal_power / noise_power)

SNR is null when no peaks are detected or when signal_power or noise_power is zero or negative.

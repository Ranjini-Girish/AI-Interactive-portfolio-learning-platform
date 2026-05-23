# Magnitude Estimation

After localization, compute a local magnitude for each localized event that has at
least `policy.min_magnitude_observations` picks with non-empty, positive `amplitude`
values among its **used** picks.

For each qualifying pick `i`, the station-event hypocentral distance is:
`dist_i = sqrt((event.x - station.x)^2 + (event.y - station.y)^2 + (event.depth + station.elevation)^2)`.

The single-station magnitude is:
`mag_i = log_base(amplitude_i) + station_amplitude_decay_power * log_base(dist_i / reference_distance_km) - log_base(reference_amplitude)`.

where `log_base` is `log10` (the `log_base` field in `magnitude_model.json` specifies base 10).

The event magnitude `ml` is the **mean** of all `mag_i` values from used picks with valid amplitudes.
The magnitude uncertainty `ml_uncertainty` is the **population standard deviation** of those `mag_i` values
(denominator = count, not count-1). If the stddev is zero, uncertainty is `0.0`.

Events with fewer than `min_magnitude_observations` valid amplitude picks get `ml: null` and `ml_uncertainty: null`.
Excluded and insufficient-picks events also get `null` magnitudes.

## Magnitude Outlier Finding

After computing the event magnitude `ml`, if any individual `mag_i` deviates from `ml` by more
than `policy.magnitude_outlier_z * ml_uncertainty`, emit a `magnitude_outlier` finding for
that pick. If `ml_uncertainty` is zero, no outlier finding is emitted.

The `deviation` field in the finding evidence is **signed**: `deviation = mag_i - ml`.
A positive deviation means the single-station estimate is above the event mean; negative
means below. The `threshold` field is the positive value `magnitude_outlier_z * ml_uncertainty`.

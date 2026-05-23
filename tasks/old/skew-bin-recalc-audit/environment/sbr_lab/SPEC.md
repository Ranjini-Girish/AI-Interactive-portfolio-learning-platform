# sbr_lab bundle

## Canonical JSON
Emit UTF-8 JSON with `json.dumps(..., sort_keys=True, indent=2, separators=(', ', ': '))` plus trailing newline.

## policy.json
`bin_edges` strictly increasing list of ints length >=2 defining half-open bins `[edges[i], edges[i+1])` for i=0..len-2.
`outlier_z` float >0 used for winsorization per probe group.
`count_band_mask` bitmask on band ids 0..3; a sample counts toward histogram iff `(count_band_mask >> band) & 1`.

## pool_state.json
`as_of` int; incidents active iff `active_from <= as_of <= active_to`.

## incidents
- `shift_bins`: fields `probe`, `delta` int (may be negative), applies to that probe's assigned bin index after winsor.
- `suppress`: drops all samples for `probe` entirely (excluded from histogram and stats).

## Binning per sample
For each sample, assign `bin_index` as largest i with `value >= edges[i]` and `value < edges[i+1]`; if value equals last edge, assign last bin i=len-2. If value below first edge, bin_index=0; if value at or above last edge, bin_index=len-2.

## Winsorization per probe
Group samples by `probe` among those not suppressed. For each group with >=2 samples, compute median m and MAD = median(|x-m|). If MAD==0, skip winsor for that probe. Else keep samples where `abs(x-m) <= outlier_z * 1.4826 * MAD`; drop others from that probe group before binning.

## Histogram
After winsor and suppression, apply `shift_bins` active incidents: for matching probe add `delta` to bin_index clamped into `[0, bin_count-1]`. Count samples per final bin among eligible band-mask samples.

## Outputs
- `histogram.json` with `bins` list length bin_count each `{index, count}` sorted by index ascending.
- `summary.json` with keys `samples_in` int (pre-suppression count), `samples_used` int (after suppression+winsor+band), `bins` int, `as_of` int.

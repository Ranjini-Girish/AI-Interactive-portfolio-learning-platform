# Dispersion kernel gap audit

Normative rules for `/app/audit/disp_gap.json`. All integers are decimal JSON numbers without floats. Canonical JSON on disk uses UTF-8, ASCII-only text, sorted object keys, two-space indent, colon+space separators, and a single trailing newline after the closing brace.

## Inputs

Read `policy.json`, `knots.json`, `catalog.json`, `incidents.json`, and `pool_state.json` from the lab directory. Each catalog entry lists a `track_id` and a `path` to a track JSON under the lab tree. Track files contain a `samples` array; every sample has `sample_id`, `lambda_q`, `n_meas_q`, `phase_q`, and `band_id` (strings).

`knots.json` holds `knots`, a non-empty list sorted by strictly increasing `lambda_q`. Each knot has `lambda_q` and `n_q` (integer refractive index in fixed-point milli-units).

`policy.json` fields: `base`, `init`, `modulus` (positive integers for the rolling digest), `current_day` (integer), `phase_jump_q` (positive integer threshold), `collapse_lambda` (boolean), and `band_bias` (object mapping `band_id` string to integer bias addend applied to the signed residual before the absolute gap).

`pool_state.json` holds optional `terminal_sum_cap`. When null or missing, no cap is applied. When present as a non-negative integer, cap logic in the summary section applies.

## Incident events

`incidents.json` contains `events`, a list of objects with `kind` and fields as follows:

- `suppress_sample`: `track_id`, `sample_id`, `start_day`, `end_day`. When `current_day` is within the inclusive day window, that sample is removed before any later step.
- `bias_band`: `band_id`, `bias_q`, `start_day`, `end_day`. When active, every remaining sample with that `band_id` gains `bias_q` added to its signed residual before `abs`.
- `compromise_track`: `track_id`, `accepted` (boolean), `day` (integer). When `accepted` is true and `current_day` is greater than or equal to `day`, the entire track is quarantined.

## Knot interpolation

Let knots be `K[0..n-1]` by increasing `lambda_q`. For sample wavelength `L`:

- If `L` equals `K[i].lambda_q` for some `i`, use `n_interp = K[i].n_q`.
- Else if `L < K[0].lambda_q`, set `n_interp = K[0].n_q` and add diagnostic `extrap_low`.
- Else if `L > K[n-1].lambda_q`, set `n_interp = K[n-1].n_q` and add diagnostic `extrap_high`.
- Else find the unique index `i` with `K[i].lambda_q < L < K[i+1].lambda_q`. With `L0,K0` from `K[i]` and `L1,K1` from `K[i+1]`, set `n_interp = K0 + floor((K1-K0)*(L-L0)/(L1-L0))` using integer division toward negative infinity as in Go and Python `//` for the product term (all operands here are non-negative in fixtures, so `//` matches floor).

## Per-track pipeline

1. Load samples, drop suppressed.
2. If `collapse_lambda` is true, group samples by `lambda_q`. Within each group sort by `sample_id` ascending and keep only the first; if any group had size greater than one, add diagnostic `lambda_collapsed` once for that track.
3. Sort remaining samples by `(lambda_q asc, sample_id asc)`.
4. Scan consecutive pairs in that order. If `abs(phase_q[j] - phase_q[i]) > phase_jump_q`, add diagnostic `phase_discontinuity` once for the track (at most once even if multiple pairs breach).
5. For each kept sample, compute `n_interp` and diagnostics from the knot step. Signed residual starts as `n_meas_q - n_interp`. Add `band_bias[band_id]` from policy when the key exists; otherwise add zero and add diagnostic `unknown_band`. Add every active `bias_band` incident `bias_q` for matching `band_id` and day window. Then `gap_mag = abs(signed_residual)`.
6. Rolling digest: start `h = init mod modulus`. For each sample in sorted order, `h = (h*base + gap_mag) mod modulus`, keeping non-negative remainder in `[0, modulus-1]`.
7. If the track is quarantined by compromise, set `status` to `quarantined`, `samples_kept` to zero, `gap_mix_steps` to zero, `terminal_digest` to zero, diagnostics to `["track_compromised"]` only, and skip numeric work on samples.

For non-quarantined tracks, `samples_kept` is the final sorted count, `gap_mix_steps` equals that count, `status` is `ok`, `terminal_digest` is final `h`, and `diagnostics` lists every diagnostic string attached during interpolation, band handling, collapse, and phase scan, sorted unique ascending.

## Pool cap scaling

Let `raw_digest` be each ok track's `terminal_digest` before scaling. Let `cap` be `terminal_sum_cap` when present. Sum `raw_digest` over ok tracks only; call this `S`. If `cap` is absent, each ok track keeps `terminal_digest = raw_digest`. If present and `S <= cap`, same. If `S > cap`, for each ok track with `raw_digest` value `r`, set `terminal_digest = floor(r * cap / S)` using integer floor division, and set summary `cap_applied` true and `scaled_sum` to the sum of these scaled digests (integer). Quarantined tracks always keep `terminal_digest` zero and are excluded from `S`.

## Output shape

Top-level keys exactly `meta`, `track_rollups`, `summary`.

`meta` contains string fields `policy_sha256`, `knots_sha256`, `catalog_sha256`, `incidents_sha256`, `pool_sha256` (lower hex SHA-256 of the respective file bytes), plus integers `base`, `init`, `modulus`, `current_day`.

`track_rollups` is a list sorted by `track_id` ascending. Each object has `track_id`, `status`, `samples_kept`, `gap_mix_steps`, `terminal_digest`, `diagnostics` (sorted unique strings).

`summary` has integers `tracks`, `total_samples_cataloged`, `total_samples_kept`, `quarantined_tracks`, and booleans `cap_applied`; `scaled_sum` is null when cap not applied or not binding, otherwise the integer sum after scaling.

`total_samples_cataloged` counts every sample object listed in catalog track files before suppression. `total_samples_kept` sums final `samples_kept` across all tracks.

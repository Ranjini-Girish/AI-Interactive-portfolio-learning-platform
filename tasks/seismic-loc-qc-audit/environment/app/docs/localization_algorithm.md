# Localization Algorithm

For each processable event, gather all eligible picks. If fewer than
`policy.min_usable_picks` are eligible, do **not** localize the event; emit one
`insufficient_picks` finding.

## Travel-Time Calculation

For a candidate position `(x_km, y_km, depth_km)` and a pick at station `st` with
phase `ph`:

```
distance = sqrt((x - st.x)^2 + (y - st.y)^2 + (depth + st.elevation)^2)
travel_time = distance / velocity(ph, depth)
```

Note: the vertical component is `depth + station.elevation` (both positive quantities
that add), **not** `depth - station.elevation`.

## Origin-Time Estimation

For each eligible pick, compute `origin_i = pick.arrival_time_s - station.bias_s - travel_time_i`.
The candidate origin time is the **weighted mean** of all `origin_i` values, using pick weights:
`origin = sum(weight_i * origin_i) / sum(weight_i)`.

## Residuals and RMS

Residual for pick `i`:
`residual_i = pick.arrival_time_s - station.bias_s - (origin_time + travel_time_i)`.
The candidate RMS is the **weighted population RMS**:
`rms = sqrt(sum(weight_i * residual_i^2) / sum(weight_i))`.

## Grid Search

1. **Coarse search**: centered on the event prior `(prior_x, prior_y, prior_depth)`.
   X and Y offsets from `-grid_radius_km` through `+grid_radius_km` **inclusive** at
   `coarse_step_km`. Depth offsets from `-depth_radius_km` through `+depth_radius_km`
   **inclusive** at `coarse_step_km`. Skip candidates where `depth < min_depth_km` or
   `depth > max_depth_km`.
2. **Fine search**: centered on the coarse winner. X, Y, and depth offsets from
   `-fine_radius_km` through `+fine_radius_km` **inclusive** at `fine_step_km`.
   Respect depth bounds.

Ties are broken by: lower RMS, then lower depth, then lower x, then lower y.

## Outlier Rejection

After the first fine solution, reject any eligible pick whose `|residual|` exceeds
`policy.residual_reject_s`. If at least `min_usable_picks` picks remain **and** any
picks were rejected, repeat the full coarse-then-fine search using only remaining picks.
If too few remain, keep the first solution and treat **all** originally eligible picks as
used. No more than one rejection pass is performed.

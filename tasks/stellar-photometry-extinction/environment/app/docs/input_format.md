# Input Files

The tool reads fixture data from `--data` (default `/app/data`).

`site.json` carries observatory metadata (name, IAU code, latitude, longitude,
altitude, time zone). The audit treats it as informational metadata; nothing in
it changes any computed value.

`instrument.json` lists the active filters in `filters` (the canonical filter
order). Every filter declared here must be processed even if no observations
are present.

`policy.json` defines:

- `min_standards_per_fit`: minimum number of standard-star observations needed
  to attempt the per-(night, filter) fit.
- `uncertainty_floor_mag`: replace any per-observation `mag_uncertainty` with
  this value when it is smaller; never use a floor below zero.
- `mad_outlier_k`: `k` in the MAD-based outlier flag (`|residual| > k · 1.4826
  · MAD`).
- `min_observations_per_lightcurve`: minimum number of calibrated observations
  required for a `(program_star, filter)` lightcurve to attempt variability
  testing.
- `variability_chi2_threshold`: a calibrated lightcurve is variable when its
  reduced chi-squared exceeds this value.
- `bad_night_residual_stddev`: residual scatter above this triggers a finding.
- `negative_extinction_threshold`: a per-(night, filter) extinction slope below
  this value triggers a finding (negative extinction is unphysical).
- `large_zero_point_uncertainty`: zero-point uncertainty above this triggers a
  finding.
- `severity_ranks`: `critical/high/medium/low/info` → integer ranks.
- `finding_severity`: maps each finding type to its severity name.

`exclusions.json` contains four arrays:

- `excluded_nights`: drop the entire night.
- `excluded_filters_per_night`: each entry is `{"night_id", "filters"}`; drop
  these filters on that night only.
- `excluded_stars`: drop these `star_id` values entirely (both as standards
  and as program stars).
- `excluded_observations`: drop these specific `image_id` values.

`manifest.json` lists each night's `night_id`, `date_utc`, and the
`observations_file` that lives under `observations/`.

`catalog/standards.csv` has header
`star_id,ra_deg,dec_deg,V_mag,B_mag,R_mag`. Empty catalog magnitude cells mean
the star has no published value in that band; observations of that star in
that filter are not eligible to constrain the extinction fit.

`catalog/programs.csv` has header `star_id,ra_deg,dec_deg,target_type`.
`target_type` is informational only.

`observations/<night_id>.csv` has header
`image_id,star_id,filter,time_utc,airmass,exposure_sec,instrumental_mag,mag_uncertainty`.
Each row is one image. `instrumental_mag` is the un-calibrated magnitude
measured for that star in that frame; `airmass` is the line-of-sight
sec(zenith) approximation.

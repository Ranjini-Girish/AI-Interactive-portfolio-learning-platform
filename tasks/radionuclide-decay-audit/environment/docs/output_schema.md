# Output Schema Reference

The auditor writes a single JSON file to `/app/output/decay_audit.json`.
Format: 2-space indent, trailing newline. All floats rounded to 6
decimal places.

## Top-Level Keys (in order)

    schema_version        integer, always 1
    summary               object
    source_sha256         object
    decay_chains          array
    sample_analyses       array
    measurement_comparisons  array
    findings              array
    zone_safety_assessment   array

## summary

    total_samples             int
    total_isotopes_tracked    int  (count of all isotopes in isotopes.json)
    total_measurements        int  (rows across all detector CSVs)
    total_anomalies           int
    total_findings            int
    chains_identified         int
    findings_by_type          object {finding_type: count}, sorted by key
    findings_by_severity      object with keys: critical, high, medium, low, info

## source_sha256

SHA-256 hex digest of every file under `/app/config/`, `/app/samples/`,
and `/app/measurements/`. Keys are paths relative to `/app/` (forward
slashes), sorted lexicographically. Files are hashed as raw bytes.

## decay_chains

Array sorted by `root_isotope`. Each entry:

    root_isotope    string
    paths           array of path objects

Each path object:

    sequence              array of isotope IDs from root to endpoint
    cumulative_branching  float (product of branching ratios along path)
    endpoint              string (last isotope in sequence)
    is_stable_endpoint    bool

## sample_analyses

Array sorted by `sample_id`. Each entry:

    sample_id              string
    initial_isotopes       sorted array of isotope IDs with initial activity
    all_chain_isotopes     sorted array of all isotopes reachable from initial
    time_snapshots         array of snapshots at measurement times
    near_degenerate_pairs  array (may be empty)
    equilibrium_checks     array

### time_snapshots

One per unique measurement time for this sample, sorted by time. Each:

    time_hours                float
    predicted_activities_bq   object {isotope_id: float}, sorted by key
    total_activity_bq         float
    dose_rate_sv_per_h        float
    above_clearance           bool

Activities below `min_activity_bq` should be set to 0.0.

### near_degenerate_pairs

One entry per parent-daughter pair where the relative difference in
decay constants falls below `nearly_equal_lambda_rel_tol`:

    parent                string
    daughter              string
    lambda_parent         float (10 decimal places)
    lambda_daughter       float (10 decimal places)
    relative_difference   float (8 decimal places)

### equilibrium_checks

For each parent-daughter pair where λ_parent < λ_daughter (potential
secular equilibrium), at each time snapshot where parent activity
exceeds `min_activity_bq`:

    parent                    string
    daughter                  string
    time_hours                float
    parent_activity_bq        float
    daughter_activity_bq      float
    expected_equilibrium_bq   float  (parent_activity × branching_ratio)
    deviation                 float  (|daughter/expected − 1|)
    in_equilibrium            bool

## measurement_comparisons

One entry per measurement row across all detector CSVs, sorted by
detector_id, then time_hours, then isotope_id:

    detector_id      string
    sample_id        string
    isotope_id       string
    time_hours       float
    predicted_bq     float
    measured_bq      float
    uncertainty_bq   float
    residual_bq      float  (measured − predicted)
    z_score          float  (|residual| / uncertainty)
    is_anomaly       bool   (z_score > anomaly_sigma_threshold)

## findings

Sorted by (severity_rank ASC, finding_type ASC, sample_id ASC,
time_hours ASC with null as −1). Each finding:

    finding_type     string
    severity         string
    sample_id        string
    time_hours       float or null
    evidence         object (keys depend on finding_type)

### Finding Types and Evidence

**dose_rate_exceeded** (critical):

    dose_rate_sv_per_h   float
    limit_sv_per_h       float

**measurement_anomaly** (high):

    detector_id    string
    isotope_id     string
    predicted_bq   float
    measured_bq    float
    z_score        float

**clearance_violation** (medium):

    total_activity_bq    float
    clearance_level_bq   float

**near_degenerate_chain** (low):

    parent                string
    daughter              string
    relative_difference   float

## zone_safety_assessment

Array sorted by zone_id. Each entry:

    zone_id                  string
    samples                  array of sample IDs
    shielding_factor         float
    max_total_activity_bq    float
    time_evaluations         array

### time_evaluations

Evaluation times are the **union** of measurement timestamps from every
detector whose measured sample appears in the zone's `samples` array.
At each evaluation time, `total_activity_bq` is the sum of predicted
Bateman-equation activities for **all** samples listed in the zone (not
just the single sample measured at that timestamp).
`unshielded_dose_rate_sv_per_h` is the combined dose rate across all
zone samples at that time. `shielded_dose_rate_sv_per_h` equals
`unshielded_dose_rate_sv_per_h` multiplied by the zone's
`shielding_factor`. `exceeds_zone_limit` is `true` when
`total_activity_bq` exceeds the zone's `max_total_activity_bq`.

Sorted by time. Each:

    time_hours                    float
    total_activity_bq             float
    unshielded_dose_rate_sv_per_h float
    shielded_dose_rate_sv_per_h   float
    exceeds_zone_limit            bool

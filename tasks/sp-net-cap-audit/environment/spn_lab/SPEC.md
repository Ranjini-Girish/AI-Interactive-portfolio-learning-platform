# Series-parallel capacitor bank audit

Normative paths live under `/app/spn_lab/`. Read every JSON file referenced below; missing files are verifier failures.

## Inputs

### Per-cap files (`caps/<cap_id>.json`)

Each file defines one capacitor instance.

- `cap_id` string, equals the filename stem.
- `c_nf` number, capacitance in nanofarads, strictly positive in the fixtures.
- `esr_mohm` number, equivalent series resistance in milliohms, non-negative. Zero means an ideal branch for parallel ESR composition.

### Rack files (`racks/<rack_id>.json`)

- `rack_id` string, equals the filename stem.
- `host_id` string, ties the rack to a host record for compromise handling.
- `rated_mv` integer, millivolts used only for stored-energy accounting on the rack’s reduced equivalent.
- `tier` string, either `alpha` or `beta`, selecting a thermal ceiling from `policy.json`.
- `stages` is a non-empty array of **stages** ordered from the high-side node toward the return node. Each stage is a non-empty array of `cap_id` strings wired in **parallel** inside that stage. Stages are connected in **series** in array order.

No `cap_id` appears in more than one rack in this dataset.

### `policy.json`

- `thermal_ceiling_uj` object mapping each tier string to a positive integer ceiling expressed in microjoules. The ceiling applies to the rack’s `energy_uj` field after reduction.
- `incident_eval_order` is always `file_order` in this dataset: replay `incident_log.json` events strictly in array index order.

### `pool_state.json`

- `current_day` integer, inclusive anchor for incident windows.
- `compromised_hosts` array of host ids. If a rack’s `host_id` is listed here, the rack is in `quarantine` regardless of other flags.
- `frozen_racks` array of `rack_id` strings. Evaluation uses **baseline** cap values for caps that belong to that rack’s topology when reducing that rack only. Baseline means the numbers read from the cap files before any incident mutations. Other racks still use the globally mutated working values for the same `cap_id` if a cap were ever shared; this dataset keeps caps disjoint per rack, but the rule remains normative.

### `incident_log.json`

`events` is an array. Each event has:

- `event_id` string, unique.
- `accepted` boolean; `false` means the event is ignored entirely.
- `start_day` and `end_day` inclusive integers. An event applies on `current_day` only when `accepted` is true and `start_day <= current_day <= end_day`.
- `kind` either `cap_scale` or `rack_esr_offset`.
- For `cap_scale`: `cap_id` and `c_mult` (positive number). Multiply that cap’s working `c_nf` in place for all later events and for racks that are not frozen with respect to that cap. For a frozen rack, the multiplier does not change the snapshot values used in its reduction, but the event still counts toward `incident_touch` if the cap participates in that rack’s topology.
- For `rack_esr_offset`: `rack_id` and `add_mohm` (non-negative number). After network reduction for that rack, add this many milliohms to the rack’s equivalent ESR unless the rack is `quarantine`. Offsets stack in file order.

### Ancillary files

`anchors/site.json` and `ancillary/meta.json` are documentation-only metadata for humans; the audit algorithm must not depend on their fields.

## Reduction math

For a rack not in `quarantine`, using either baseline or working per-cap snapshots as dictated by the frozen rule:

1. **Parallel stage**: sum all `c_nf`. For ESR, convert each branch conductance `g = 1 / esr_mohm` when `esr_mohm > 0`. If any participating branch has `esr_mohm == 0`, the stage’s equivalent ESR is `0`. Otherwise `equiv_esr = 1 / (sum of g)`.
2. **Series string of stages**: `inv_c = sum(1 / stage_c_nf)`; `equiv_c_nf = 1 / inv_c`. Sum stage equivalent ESRs for the string ESR before offsets.
3. Apply any `rack_esr_offset` events that target this rack in chronological order after reduction.

Stored energy on the reduced equivalent uses volts `V = rated_mv / 1000` with `C_farads = equiv_c_nf * 1e-9`. Let `energy_uj = round(0.5 * C_farads * V * V * 1e6)` as an integer microjoules. For `quarantine` racks, force `equiv_c_nf = 0`, `equiv_esr_mohm = null`, `energy_uj = 0`.

`headroom_uj = thermal_ceiling_uj[tier] - energy_uj` for non-quarantine racks. For `quarantine` racks set `headroom_uj` to JSON `null`.

## Rack state and reasons

States:

- `quarantine` when the host is compromised. Emit `reasons = ["host_compromised"]` only.
- Otherwise `degraded` when any of: `headroom_uj < 0`; an applied `cap_scale` names a `cap_id` present in that rack’s topology; an applied `rack_esr_offset` names the rack. Reasons must be sorted ASCII ascending, deduplicated: `negative_headroom`, `incident_touch`, `esr_offset` using those exact spellings. The `incident_touch` token is emitted only for qualifying `cap_scale` events, never solely because of `rack_esr_offset`.
- Otherwise `ok` with `reasons = []`.

## Outputs under `/app/spn_audit/`

Write UTF-8 JSON with ASCII-only text, two-space indent, sorted object keys, and a single trailing newline after each file.

### `rack_equivalents.json`

Top-level `racks` array sorted by `rack_id`. Each record includes `rack_id`, `equiv_c_nf`, `equiv_esr_mohm` (number or null), `energy_uj`, `headroom_uj` (integer for non-quarantine racks, JSON `null` when `quarantine`), `state`, `reasons` array.

Numeric rounding: emit `equiv_c_nf` and `equiv_esr_mohm` with exactly three decimal places as JSON numbers (strings are forbidden). `quarantine` uses `0.000` and `null` for ESR.

### `incident_applied.json`

`applied` array, one entry per accepted event that satisfied its day window, in replay order. Fields sorted per object: `detail` (string human-readable summary chosen deterministically per kind), `event_id`, `kind`.

### `cap_working.json`

Object mapping each `cap_id` to an object with keys `c_nf` and `esr_mohm` reflecting the working values after all incidents are replayed (global path), numbers with three decimals where applicable. Sort keys ascending.

### `summary.json`

Fields sorted: `min_headroom_uj` (minimum `headroom_uj` among racks not `quarantine`, or `null` if none), `rack_count` integer, `states` object with keys `degraded`, `ok`, `quarantine` counting racks, `total_energy_uj` integer sum of all `energy_uj`.

## Determinism

All sorts are ASCII ascending. Use the frozen snapshot rule exactly as written; do not infer additional physics.

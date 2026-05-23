# Ridge guard merge audit (normative)

All JSON read by the auditor must be UTF-8. Parse errors, unknown enum values, missing required keys, or type mismatches are malformed input: the auditor exits non-zero and must not create any output file named in section 7.

## 1. Canonical JSON (output)

Serialize every output object with `json.dumps(obj, ensure_ascii=True, sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline (`\n`). No BOM.

## 2. Input inventory

Under the data directory (default `/app/rgma_lab/`):

- `SPEC.md` (this file; witness only for hashing)
- `policy.json`
- `domain_layout.json`
- `pool_state.json`
- `incident_log.json`
- `anchors/day_floor.json`
- `anchors/window.json`
- `ancillary/meta.json`
- `ancillary/notes.json`
- `hosts/*.json` one file per host; filename is ignored; identity is `host_id` inside the file

## 3. Host record schema

Each `hosts/*.json` object must contain:

- `host_id` string (unique across all host files)
- `tier` one of `gold`, `silver`, `bronze`
- `raw_lambda` finite number (may be mutated by incidents)
- `bias_signal` finite number

## 4. Policy schema

`policy.json` fields:

- `day_start`, `day_end` integers inclusive window for the lab day index
- `tiers` object mapping each of `gold`, `silver`, `bronze` to a finite positive scale factor
- `signal_cutoff` finite non-negative number
- `lambda_cap` finite positive cap on post-merge microlambda magnitude (see section 6)
- `alias_guard` boolean

## 5. Anchor factor

Read `anchors/day_floor.json` with integer `floor_day`. Let `D0 = max(policy.day_start, floor_day)` and `D1 = policy.day_end`. If `D1 < D0`, malformed input.

Let `A = anchors/window.json` with integer `start` and `end` inclusive.

Overlap days `O` is the count of integers `d` such that `d >= max(D0, A.start)` and `d <= min(D1, A.end)`. If that range is empty, `O = 0`.

Let `K = min(O, 5)`. Anchor factor `F = 1 + 0.01 * K` (floating-point; use IEEE-754 binary double throughout).

## 6. Incident application

`incident_log.json` is an array of objects, each with integer `seq` (unique), string `kind`, and fields:

- `bump_lambda`: requires `host_id`, finite `delta`
- `freeze_host`: requires `host_id`
- `lift_freeze`: requires `host_id`

Sort incidents by ascending `seq`. For ties on `seq`, sort by ascending `kind` string, then ascending `host_id` if present, then ascending JSON text of the incident object with keys sorted (UTF-8, `separators=(",", ":")`, `ensure_ascii=True`).

Apply in that order:

- `bump_lambda`: if the host exists and is not currently frozen, add `delta` to its `raw_lambda`
- `freeze_host`: mark host frozen (if unknown host id, ignore)
- `lift_freeze`: clear frozen flag (if unknown host id, ignore)

Hosts not mentioned in any host file are unknown.

## 7. Outputs

Write two files into the audit directory (default `/app/audit/`):

### `ridge_report.json`

Top-level keys exactly: `anchor_factor`, `entries`, `schema_version`.

- `schema_version` is the integer `1`
- `anchor_factor` is JSON number `float(f"{F:.12f}")` using Python 3 f-string formatting then float cast
- `entries` is an array sorted by ascending `host_id` string (byte-wise UTF-8 / Unicode code-point order as JSON strings)

Each entry object keys exactly: `host_id`, `microlambda`, `bias_class`, `tier`.

- `tier` repeats the host tier after incidents (tier never changes)
- If the host is frozen at the end of incident processing: `microlambda` is JSON `null` and `bias_class` is the string `frozen`
- Otherwise compute `S = raw_lambda * tiers[tier] * F` using Python float multiplication. Let `s` be `format(S, ".17g")` from Python 3. Convert to microlambda integer `M = int((Decimal(s) * Decimal("1000000")).to_integral_value(rounding=ROUND_HALF_EVEN))` using `Decimal` and `ROUND_HALF_EVEN` from Python's `decimal` module

### Alias merge (only if `alias_guard` is true)

After computing each unfrozen host's preliminary `M` independently, build an undirected graph on host ids that exist, are not frozen, and appear in at least one alias row. For each alias group in `ancillary/meta.json` key `alias_groups` (array of arrays of host ids), take the filtered set of members that exist and are not frozen; if that set has fewer than two ids, skip the row. Otherwise add an undirected edge between every unordered pair of distinct ids in the filtered set (a clique on that row).

Let each connected component in that graph inherit `M_comp = max(M)` over every host id in the component using each host's preliminary `M` before this subsection runs. For every host id that lies in a component with at least two vertices, replace its `M` with `M_comp`. Host ids that are isolated in this graph (degree zero after all rows are applied) keep their preliminary `M`.

If `alias_guard` is false, skip this entire subsection.

### Cap

Let `cap_s` be `format(float(policy.lambda_cap), ".17g")`. Let `C = int((Decimal(cap_s) * Decimal("1000000")).to_integral_value(rounding=ROUND_HALF_EVEN))`. For every unfrozen host, replace `M` with `min(M, C)`.

### `bias_class` for unfrozen hosts

Let `t = policy.signal_cutoff`. If `bias_signal > t` then `high`. If `bias_signal < -t` then `low`. Else `mid`.

### `summary.json`

Top-level keys exactly: `anchor_overlap_days`, `entries_total`, `frozen_total`, `lambda_cap_micro`, `merged_groups`, `schema_version`.

- `schema_version` is `1`
- `anchor_overlap_days` is the integer `O`
- `entries_total` is count of host files (not unique guard; must equal number of objects loaded from `hosts/*.json`)
- `frozen_total` is count of hosts frozen at end
- `lambda_cap_micro` is `C` as integer
- `merged_groups` is count of alias groups where `alias_guard` is true and the filtered live group size is at least 2

## 8. Witness files

`pool_state.json` and `domain_layout.json` must be byte-identical to the shipped fixtures after the run (the auditor must not rewrite them).

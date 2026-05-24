# Output Format Specification

The output file is `/app/output/complexity_audit.json` — a JSON object with 2-space indentation, sorted keys at every nesting level, and a trailing newline.

## Top-Level Keys

- `findings` — array of all findings across all modules (globally sorted)
- `module_audits` — array of per-module audit results, sorted by module_name
- `schema_version` — integer, always 1
- `source_hashes` — object mapping relative module file paths to SHA-256 hex digests
- `summary` — aggregate statistics object

## Summary Object

- `aggregate_risk_score` — geometric mean of all positive risk scores, 6 decimals. If no findings, 0.0
- `avg_cyclomatic` — harmonic mean of all function CC values across all modules, 6 decimals
- `avg_cognitive` — harmonic mean of all function CogC values across all modules, 6 decimals. Functions with CogC = 0 are excluded from harmonic mean (cannot divide by zero)
- `avg_maintainability` — arithmetic mean of all module MI values, 6 decimals
- `findings_by_severity` — object with keys "critical", "high", "medium", "low", "info" (all five must be present, even if 0)
- `total_findings` — integer count of all findings
- `total_functions` — integer count of all functions
- `total_modules` — integer count of all modules

## Module Audit Object

- `coupling` — object with `afferent`, `efferent`, `instability` (float, 6 decimals), `abstractness` (null), `distance` (null)
- `findings` — array of findings for this module
- `functions` — array of function metric objects, sorted by function_name
- `halstead` — module-level Halstead aggregates: `avg_difficulty`, `max_difficulty`, `total_effort`, `total_volume` (all 6 decimals)
- `maintainability_index` — module-level MI (arithmetic mean of function MIs), 6 decimals
- `module_name` — string
- `path` — string (from module data)
- `summary` — object with `avg_cyclomatic` (harmonic mean of function CCs, 6 decimals; functions with CC=0 excluded), `avg_cognitive` (harmonic mean of function CogCs, 6 decimals; 0-value functions excluded), `max_cyclomatic`, `max_cognitive`, `total_functions`

## Function Metrics Object

- `cognitive_complexity` — integer
- `cyclomatic_complexity` — integer
- `function_name` — string
- `halstead` — object with `bugs`, `difficulty`, `effort`, `length`, `time`, `vocabulary`, `volume` (all 6 decimals except vocabulary and length which are integers)
- `lines` — integer
- `maintainability_index` — float, 6 decimals
- `parameters` — integer (count of parameters)

## Source Hashes

Compute SHA-256 of each module JSON file under `data/modules/`. The hash is computed on file content after normalizing line endings to `\n` and stripping a single trailing newline if present. Keys are relative paths from `/app/` (e.g., `data/modules/auth_handler.json`).

## Harmonic Mean

The harmonic mean of values v₁, v₂, …, vₙ is: `n / (1/v₁ + 1/v₂ + … + 1/vₙ)`. Values equal to 0 must be excluded (they would cause division by zero). If all values are 0 or the set is empty, the harmonic mean is 0.0.

## Geometric Mean

The geometric mean of values v₁, v₂, …, vₙ is: `exp(mean(ln(v₁), ln(v₂), …, ln(vₙ)))`. Only positive values are included. If empty, result is 0.0. Round to 6 decimal places.

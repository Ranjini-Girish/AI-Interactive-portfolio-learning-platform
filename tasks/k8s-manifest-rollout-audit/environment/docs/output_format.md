# Output format

All three files live under `/app/output/`:

- `manifest_drift.json`
- `chart_impact.json`
- `rollout_plan.json`

Each file must be UTF-8, JSON-encoded with `indent=2`, and end with exactly one trailing newline character. Two correct runs must produce **byte-identical** files.

The drift report contains the SHA-256 digests of the raw `/app/data/baseline-manifests.yml` and `/app/data/current-manifests.yml` files (lowercase hex, 64 chars). Compute the digest from the on-disk bytes; do not normalize whitespace or re-emit YAML.

Top-level shapes follow the JSON Schemas under `/app/schemas/` (mirrored at `environment/schemas/` in the source tree).

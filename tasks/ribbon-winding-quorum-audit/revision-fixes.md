# Revision fixes — c0f4de24-3ef0-447e-a93a-311e67b21bb4

## Platform feedback (prior submission)

- **difficulty_trivial** — Opus 100% (5/5), GPT-5.2 100% (5/5); algorithm was a straight SPEC translation.
- **behavior_in_tests** — Go binary / on-disk JSON presentation not verified; Python-only bypass possible.
- **autoeval_build_failed** — oversized `golang:1.23-bookworm` base caused 7200s build timeout.

## Fixes applied (2026-05-24, pass 2)

### Difficulty hardening (interacting rules, SPEC retained)

- [x] **Anchor saturation** — `anchor_saturation_step` in `policy.json`; boost is `anchor_weight + step * (hits - 1)` when hits ≥ 1 (not linear `weight * hits`).
- [x] **Incident relax composition** — overlapping windows **sum** relax values, capped at `quorum - relax_cap_margin` via new `relax_cap_margin` policy field.
- [x] **Tier-floor trimming** — `tier_floor` in `pool_state.json`; capacity sums use `max(0, effective_witness - floor)` only during trimming.
- [x] **Fixture retune** — second alpha incident window, tighter `tier_cap` / floors so all verdict enums still appear with new math.
- [x] **Semantic tests** — `TestCompoundRules` asserts saturation witness, summed-relax quorum, and `tier_trimmed` presence.

### QC / test-quality gaps

- [x] **Go enforcement** — `TestImplementationArtifacts` requires `/app/src/*.go` with `package main`, executable `/app/bin/rwqaudit`, and subprocess reruns under `RWQ_*` overrides.
- [x] **On-disk JSON** — `test_on_disk_bytes_match_canonical_minified_json` + existing single-newline check verify minified presentation (no 2-space indent; SPEC uses minified canonical JSON).
- [x] **Input immutability** — pinned `EXPECTED_INPUT_HASHES` unchanged lab bytes; instruction states ancillary files must remain untouched.

### Build / harness

- [x] **Dockerfile slim base** — `debian:bookworm-slim@sha256:f9c6a2…` + apt `golang-go` (replaces full `golang:1.23-bookworm`).
- [x] **Oracle layout** — `solve.sh` builds from `/app/src/` to `/app/bin/rwqaudit`; `go.mod` pinned to `go 1.19` for bookworm toolchain.
- [x] **Offline verifier** — pytest preinstalled in Dockerfile; `tests/test.sh` thin wrapper; `allow_internet = false`.
- [x] **Harness deps** — `tmux`, `asciinema` on apt line.

### Hash locks refreshed

- All `EXPECTED_*` dicts in `tests/test_outputs.py` recomputed against updated fixtures + oracle.

## Verification

| Gate | Result |
|---|---|
| `terminus_zip.py preflight` | **PASS** (exit 0 — ruff, leakage, env 24 files / `small`, workdir + allow_internet, test.sh, tmux/asciinema) |
| Docker oracle + pytest | **15/15 passed** on `rwq-preflight` slim image |

## Expected difficulty impact

Prior agents scored 100% by translating a linear SPEC pipeline (often in Python). The three interacting twists compound errors:

1. Wrong relax aggregation (max vs sum) shifts alpha `effective_quorum` and downstream trimming.
2. Linear anchor boost mis-ranks beta segments and changes trim victims.
3. Ignoring tier floors over-trims or under-trims capacity.

Agents must implement the full composed pipeline **and** ship a Go binary to pass subprocess + artifact tests. Expect pass rates to drop toward the **HARD** band (target ≤20% best model or ≤20% worst when best >20%).

## Resubmit

Upload with revision task id `c0f4de24-3ef0-447e-a93a-311e67b21bb4` after cycle-1 rubric regen.

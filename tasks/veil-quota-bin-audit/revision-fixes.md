# Revision fixes — 021f9c95-f7c9-4d2f-b684-796382447238

## Platform feedback (from `e2e/audit/revision-021f9c95-f7c9-4d2f-b684-796382447238-context.json`)

| Signal | Detail |
|---|---|
| **agents_unsolvable** | 0/5 both models; universal failures on `tail_ledger_sha` / `veil_bins.json` schema; masks never matched fixtures. |
| **behavior_in_tests** | `incident_log.json` used `sbr_*` IDs while fixtures are `vqb_*` — masking path unverified. |
| **structured_data_schema** | `veil_bins.json` per-sample histogram row schema (`bin`, `tally`) not normatively defined. |
| **behavior_in_task_description** | Prior pass deferred `tail_ledger_sha` / `total_assignments` to “latch audit”. |
| **Difficulty** | HARD (Opus 0/5, GPT-5.2 0/5). Solvability gate failed until spec gaps closed. |

## Fixes applied (2026-05-24, pass 2)

- [x] **Mask fixture alignment** — `incident_log.json` now masks `vqb_04` (slot 1) and `vqb_09` (slots 0, 2) so the union-zero path changes oracle output and hash locks reject skipped masking.
- [x] **SPEC normative mask + fold rules** — inlined mask union semantics and prefix-fold steps; removed “latch task / latch audit” cross-references for pipeline steps.
- [x] **SPEC `veil_bins.json` schema** — documents `samples` → bare array of `{bin, tally}` objects per sample id (no wrapper object).
- [x] **SPEC `tail_ledger_sha` / `total_assignments`** — retained normative definitions from pass 1 (SHA-256 of sorted `{sample_id}:{S[n]}`; post-mask reading count sum).
- [x] **Tests** — regenerated input/output/field hashes; added `test_histogram_rows_use_bin_and_tally` and `test_incident_masks_reference_fixture_samples`.
- [x] **Dockerfile / verifier** — unchanged (slim debian, offline pytest, tmux/asciinema).

## Verification

| Gate | Result |
|---|---|
| Local pytest (Python oracle mirror, 9 tests) | **PASS** |
| `terminus_zip.py preflight` | **PASS** (ruff, leakage, env 22 files / `small`, workdir + allow_internet, test.sh, tmux/asciinema) |
| Leakage grep (instruction, tests, SPEC, rubrics) | **PASS** |

## Solvability gaps addressed

| Gap | Fix |
|---|---|
| Undefined “latch audit” for tail hash / assignment count | Normative formulas in SPEC (pass 1); prefix-fold steps inlined (pass 2). |
| `veil_bins.json` array vs wrapper ambiguity | SPEC states each sample maps directly to a histogram array; tests assert `{bin, tally}` keys. |
| `"tally"` field name never named | SPEC + test `test_histogram_rows_use_bin_and_tally`. |
| Masking code path never exercised | `incident_log.json` IDs aligned to `vqb_*`; output hashes regenerated. |

## Files changed

- `environment/vqb_lab/incident_log.json` — `sbr_*` → `vqb_*` mask targets
- `environment/vqb_lab/SPEC.md` — mask/fold inlining, `veil_bins.json` row schema, normative summary fields
- `tests/test_outputs.py` — hash lock updates + schema/mask coverage tests
- `revision-fixes.md` — this note

## Blockers

- **None for local preflight.** Resubmit for platform QC + agent trials to confirm solvability gate clears.

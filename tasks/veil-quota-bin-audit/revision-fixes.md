# Revision fixes — 021f9c95-f7c9-4d2f-b684-796382447238

## Platform feedback (from `e2e/audit/revision-021f9c95-f7c9-4d2f-b684-796382447238-context.json`)

| Signal | Detail |
|---|---|
| **autoeval_build_failed** | Initial CodeBuild FAILED (`5803a165-…`). A later portal static-check run on the same revision card reported **SUCCEEDED** (`1008a177-…`) after the slim Dockerfile was already in tree. |
| **behavior_in_task_description** | QC flagged `summary.json.tail_ledger_sha` and `summary.json.total_assignments`: SPEC listed keys but deferred to “latch audit” without normative definitions. |
| **Difficulty** | HARD (Opus 0/5, GPT-5.2 0/5 on last full eval). Solvability gate satisfied. |

## Fixes applied (2026-05-24)

- [x] **SPEC normative text** — `environment/vqb_lab/SPEC.md` now defines `tail_ledger_sha` (SHA-256 of sorted `{sample_id}:{S[n]}` strings) and `total_assignments` (sum of post-mask reading counts). Removed cross-task “latch audit” deferral for those fields.
- [x] **SPEC hash lock** — updated `EXPECTED_INPUT_HASHES["SPEC.md"]` in `tests/test_outputs.py` to match revised SPEC bytes.
- [x] **Dockerfile** — already on `debian:bookworm-slim@sha256:f9c6a2…` + apt `golang-go`; `tmux`, `asciinema`, offline pytest preinstalled. No change required.
- [x] **Oracle-pending leakage** — no `# scaffold-status: oracle-pending` line present; leakage grep clean on reviewer-visible files.
- [x] **Zip hygiene** — `clean` + `build`; E2E metadata (`platform-submission.json`, `revision-*.json`, `revision-audit.log`) excluded from archive by `terminus_zip.py`.

## Verification

| Gate | Result |
|---|---|
| `terminus_zip.py preflight` | **PASS** (ruff, leakage, env 22 files / `small`, workdir + allow_internet, test.sh, tmux/asciinema) |
| `terminus_zip.py verify-task` | **PASS** |
| Docker oracle + pytest | **Not re-run this pass** (local image build skipped; oracle logic unchanged) |

## Resubmit artifact

| Field | Value |
|---|---|
| Path | `tasks/veil-quota-bin-audit.zip` |
| Bytes | 13,879 |
| SHA-256 | `36893d4fc0d340e7232e1b4df71a5d3e686268c9e97583cd4af8ace2924b342e` |

## Files changed

- `environment/vqb_lab/SPEC.md` — normative `tail_ledger_sha` / `total_assignments` definitions
- `tests/test_outputs.py` — `SPEC.md` input hash update
- `revision-fixes.md` — this note

## Blockers

- **None for local preflight.** Platform QC must be re-run on resubmit to confirm `behavior_in_task_description` clears.
- **No E2E submit** performed in this pass (fix-only per assignment).

# Revision fixes — c0f4de24-3ef0-447e-a93a-311e67b21bb4

## Platform feedback

- **Build Completion Timeout (7200s)** on difficulty check — no artifact; UI reported generic oracle failure while the root cause was the oversized `golang:1.23-bookworm` base image (~1GB+).
- Prior static checks and quality checks were otherwise green; agent trials never started.

## Fixes applied (2026-05-24)

- [x] **Dockerfile slim base** — already migrated to `debian:bookworm-slim@sha256:f9c6a2…` + apt `golang-go` (replaces full `golang:1.23-bookworm`).
- [x] **Go module pin** — `solution/go.mod` `go 1.19` to match bookworm `golang-go` with `GOTOOLCHAIN=local`.
- [x] **Instruction alignment** — dropped hard-coded "Go 1.23" from `instruction.md` (paths and four output files unchanged).
- [x] **Harness deps** — `tmux`, `asciinema`, `python3`, `pytest==8.4.1`, `pytest-json-ctrf==0.3.5` preinstalled at image build; `python` → `python3` symlink present.
- [x] **Offline verifier** — `tests/test.sh` uses direct `python3 -m pytest` with canonical reward block; `[environment].allow_internet = false` set.
- [x] **Oracle-pending / leakage** — `tests/test_outputs.py` carries finalized hash locks only; leakage grep clean (no `solve.sh`, `solution/`, or `oracle` strings in reviewer-visible files).
- [x] **Dev artifact cleanup** — removed `revision-audit.log`, `platform-submission.json`, `revision-context.json`, `revision-params.json` from the task folder (excluded from zip by `terminus_zip.py build`).

## Verification

| Gate | Result |
|---|---|
| `terminus_zip.py preflight` | **PASS** (ruff, leakage, env 23 files / `small`, workdir + allow_internet, test.sh, tmux/asciinema) |
| Docker oracle (`bash /solution/solve.sh`) + pytest | **9/9 passed** on slim image `rwq-preflight` |
| `terminus_zip.py verify-task` | **PASS** |

## Resubmit artifact

| Field | Value |
|---|---|
| Path | `tasks/ribbon-winding-quorum-audit.zip` |
| Entries | 31 |
| Bytes | 16,268 |
| SHA-256 | `25e3ebd916bd736d88a32b993aa7b9b08a3fb032d50b7028ebc98c7f459b7695` |

## Blockers

- None for local preflight / zip build.
- **Platform re-submit required** to confirm difficulty check completes under the 7200s budget with the slim image (not run in this pass).

## Notes

- `task.toml` retains `workdir = "/app"` per repo preflight static-check requirement.
- No browser E2E submit performed in this pass (fix-only).

# Revision fixes — a711d7b8-a9a9-4e40-88e9-95d3272ac3e1

## Platform feedback found

- **No `revision-audit.log`** in the upload dir at extract time.
- **`platform-submission.json`**: prior submit **2026-05-23**, status **Evaluation pending** (revision flow, `sendToReviewer: true`). No human reviewer remarks or AutoEval failure text captured locally yet.
- **Tracker / queue**: listed as **resubmitted 2026-05-23** in `NEEDS_REVISION_QUEUE.md`; duplicate UUID `943ca427` skipped (same slug).

## Wave 2 hardening (2026-05-24)

- [x] **Dockerfile slim base** — replaced `golang:1.23-bookworm` (~1GB+) with `debian:bookworm-slim@sha256:f9c6a2…` + apt `golang-go` to avoid CodeBuild **7200s Build Completion Timeout** misreported as oracle failure.
- [x] **Go module pin** — `solution/go.mod` `go 1.19` to match bookworm `golang-go` with `GOTOOLCHAIN=local`.
- [x] **Harness deps** — `tmux`, `asciinema`, `python3`, `pytest==8.4.1`, `pytest-json-ctrf==0.3.5` preinstalled at image build; `python` → `python3` symlink added.
- [x] **Offline verifier** — `tests/test.sh` unchanged (direct `python3 -m pytest`, canonical reward block, no runtime installs); `[environment].allow_internet = false` already set.
- [x] **Cleanup** — removed unused dev duplicate `solution/main.go` (oracle builds from `replag.go` only).
- [x] **Leakage grep** — clean on `instruction.md`, `tests/test_outputs.py`, `environment/replag/SPEC.md`, `rubrics.txt`.

## Verification

| Gate | Result |
|---|---|
| `terminus_zip.py preflight` | **PASS** (ruff, leakage, env 24 files / `small`, workdir + allow_internet, test.sh, tmux/asciinema) |
| Docker oracle (`bash /solution/solve.sh`) + pytest | **19/19 passed** on slim image `rla-oracle` |
| `terminus_zip.py verify-task` | **PASS** |

## Resubmit artifact

| Field | Value |
|---|---|
| Path | `tasks/replica-lag-window-audit.zip` |
| Bytes | 23,799 |
| SHA-256 | `b2b40cea891845dfc2a5fb1aba89e85d7b4e469da859c28014e126684b2f4c61` |

## Notes

- Prior zip SHA was `bdf16a9184f86a7d3da30227c73da30893f8d40121c894a1c7657145194c7048` (26,727 bytes); slim Dockerfile + `main.go` removal reduced archive size.
- `task.toml` retains `workdir = "/app"` per repo preflight static-check requirement.
- No browser submit performed in this pass (fix-only).

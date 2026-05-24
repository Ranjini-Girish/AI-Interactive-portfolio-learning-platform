# Revision fixes — 9c8fef7e-cac5-4076-a8b8-c5e1fe8c2235

## Platform feedback (likely)

- **Build Completion Timeout (7200s)** — full `golang:1.23-bookworm` base (~1GB+) can exceed CodeBuild budget; UI may misreport as **Oracle solution failed** with no difficulty-check artifact.

## Wave 2 hardening (2026-05-24)

- [x] **Dockerfile slim base** — replaced `golang:1.23-bookworm` with `debian:bookworm-slim@sha256:f9c6a2…` + apt `golang-go`, `tmux`, `asciinema`, `python3`, pinned `pytest==8.4.1` / `pytest-json-ctrf==0.3.5`; added `python` → `python3` symlink.
- [x] **Go module pin** — `solution/go.mod` `go 1.19` to match bookworm `golang-go` with `GOTOOLCHAIN=local`.
- [x] **Oracle build path** — removed stale `PATH=/usr/local/go/bin` from `solution/solve.sh` (apt `go` only).
- [x] **Scaffold cleanup** — removed `# scaffold-status: oracle-pending` from `tests/test_outputs.py`.
- [x] **Offline verifier** — `[environment].allow_internet = false` unchanged; `tests/test.sh` retains crash-safe trap + canonical reward block (no runtime installs).
- [x] **Leakage grep** — clean on `instruction.md`, `tests/test_outputs.py`, `environment/leb_lab/SPEC.md`, `rubrics.txt`.

## Verification

| Gate | Result |
|---|---|
| `terminus_zip.py preflight` | **PASS** (ruff, leakage, env 22 files / `small`, workdir + allow_internet, test.sh, tmux/asciinema) |
| `terminus_zip.py verify-task` | **PASS** |
| Docker oracle + pytest | **Not run** (fix-only pass; slim image build not timed locally) |
| Platform E2E submit | **Skipped** per revision scope |

## Resubmit artifact

| Field | Value |
|---|---|
| Path | `tasks/latch-echo-bin-audit.zip` |
| Bytes | 13,975 |
| SHA-256 | `8753eefac24285abac76f82e695a1f5fa3fd2509378255a4a8d7accb05511cff` |

## Files changed

| File | Change |
|---|---|
| `environment/Dockerfile` | Slim debian base + apt toolchain / harness / verifier deps |
| `solution/go.mod` | `go 1.23` → `go 1.19` |
| `solution/solve.sh` | Drop `/usr/local/go/bin` PATH override |
| `tests/test_outputs.py` | Remove scaffold-status comment |
| `tests/test.sh` | Comment header aligned with offline-verifier pattern |

## Blockers

None for static preflight / zip build. **Recommended before platform resubmit:** timed local `docker build` + oracle pytest on slim image to confirm Go build succeeds under apt `golang-go`.

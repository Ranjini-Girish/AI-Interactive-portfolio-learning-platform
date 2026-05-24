# Revision fixes — 9c8fef7e-cac5-4076-a8b8-c5e1fe8c2235

## Human reviewer blocker

- **reviewer_hash_lock_fixture_gap** — verifier relied only on bundled input/output hash locks; a solution could pass by memorizing this dataset without implementing the latch pipeline generally.

## Wave 2 hardening (2026-05-24)

- [x] **Dockerfile slim base** — `debian:bookworm-slim@sha256:f9c6a2…` + apt `golang-go`, `tmux`, `asciinema`, `python3`, pinned `pytest==8.4.1` / `pytest-json-ctrf==0.3.5`; `python` → `python3` symlink.
- [x] **Go module pin** — `solution/go.mod` `go 1.19` to match bookworm `golang-go` with `GOTOOLCHAIN=local`.
- [x] **Oracle build path** — removed stale `PATH=/usr/local/go/bin` from `solution/solve.sh` (apt `go` only).
- [x] **Offline verifier** — `[environment].allow_internet = false`; `tests/test.sh` retains crash-safe trap + canonical reward block (no runtime installs). **pytest stays in Dockerfile** per May 2026 offline-verifier requirement (reviewer note acknowledged; not moved to runtime install).
- [x] **Leakage grep** — clean on `instruction.md`, `tests/test_outputs.py`, `environment/leb_lab/SPEC.md`, `rubrics.txt`.

## Wave 3 — alternate fixture (2026-05-24)

- [x] **`TestAlternateGeneratedFixture`** — writes a synthetic one-sample lab (mask + latch-echo + echo-max) under `tmp_path`, reruns the agent/oracle binary with `LEB_DATA_DIR` / `LEB_AUDIT_DIR`, and compares `latch_bins.json` + `summary.json` to an in-test `_compute_reference()` re-derivation from SPEC.md (not copied from Go oracle).
- [x] **Primary hash locks retained** — `EXPECTED_INPUT_HASHES`, `EXPECTED_OUTPUT_CANONICAL_HASHES`, and `EXPECTED_FIELD_HASHES` unchanged; no input fixture edits required.

## Verification

| Gate | Result |
|---|---|
| `terminus_zip.py preflight` | **PASS** (ruff, leakage, env 22 files / `small`, workdir + allow_internet, test.sh, tmux/asciinema) |
| Docker oracle (`bash /solution/solve.sh`) + pytest | **8/8 passed** on slim image `leb-preflight` (includes alternate generated fixture) |
| `terminus_zip.py build` | **PASS** |

## Resubmit artifact

| Field | Value |
|---|---|
| Path | `tasks/latch-echo-bin-audit.zip` |
| Entries | 31 |
| Bytes | 18,063 |
| SHA-256 | `d4d7b1db967b9e7ae7e578b42fd1e4526c266535b65e3e29ad57a07240f669fa` |

## Files changed

| File | Change |
|---|---|
| `tests/test_outputs.py` | Added `_compute_reference()`, `_write_generated_lab()`, `TestAlternateGeneratedFixture`; binary discovery via `/app/_leb_build/leb` and sibling paths |
| `revision-fixes.md` | This note |

## Blockers

None for static preflight / zip build / local oracle pytest.

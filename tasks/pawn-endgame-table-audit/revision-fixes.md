# Revision fixes — faf82617-f62d-4b79-acfb-4f4e0aa3bce0

## Portal feedback (resolved)

- [x] **AutoEval build FAILED** — replaced `FROM golang:1.23-bookworm` (~1.2 GB) with `debian:bookworm-slim` + apt `golang-go`, `tmux`, `asciinema`, and offline pytest. Full golang toolchain images routinely exceed the platform 7200s build budget and surface as generic build/oracle failure.
- [x] **Solvability: some tests not passed by any agent run** — see diagnosis below; instruction + Dockerfile fixes restore an agent-achievable path while keeping MEDIUM difficulty.
- [x] **task.toml difficulty** — set to `medium` to match empirical band (opus 60%, gpt5-2 40%).

## Changes made

| File | Fix |
|------|-----|
| `environment/Dockerfile` | Slim Debian base; preinstall `golang-go`, `tmux`, `asciinema`, `python3`, pytest; add `python` → `python3` symlink |
| `solution/solve.sh` | `go 1.19` in generated `go.mod` (matches Debian bookworm `golang-go`); extend `PATH` with `/usr/bin` for slim image |
| `instruction.md` | Split into two paragraphs; state pawnaudit is **argv-free** and reads `PET_DATA_DIR` / `PET_AUDIT_DIR`; require native **ELF** binary |
| `task.toml` | `difficulty = "medium"` |
| `rubrics.txt` | Mirror argv-free / ELF contract in positive criteria |

## Solvability diagnosis

**Root cause (build):** The shipped image used `golang:1.23-bookworm`, which is too large for CodeBuild’s combined build + difficulty-check window. Build failure prevents the oracle phase from completing reliably, which the platform reports alongside solvability warnings even when partial agent stats exist.

**Root cause (spec gap):** `tests/test_outputs.py::TestCompiledBinary::test_pawnaudit_binary_regenerates_canonical_reports` invokes `/app/bin/pawnaudit` with **no positional arguments**, only `PET_DATA_DIR` / `PET_AUDIT_DIR` env overrides. The prior `instruction.md` did not state the argv-free contract; agents that implement `pawnaudit <data> <out>` pass hash checks when they hand-write JSON to `/app/audit` but fail all four `TestCompiledBinary` tests on every run. That pattern yields **0% per-test pass rate** on the binary-regeneration and ELF-metadata checks even when semantic output tests pass on other trials.

**Why MEDIUM is preserved:** Agent runs already land at 40–60% full reward; the task still requires composing incident freezes, opposition tie-breaks, tempo windows, and cap bands from SPEC.md. Fixes remove infra/spec blockers without simplifying the algorithm.

**Likely never-passed tests (pre-fix):**

1. `test_pawnaudit_binary_regenerates_canonical_reports`
2. `test_pawnaudit_binary_is_native_executable` (when agents skip `go build` and write JSON or shell wrappers)
3. `test_pawnaudit_binary_built_from_go` (same skip-build path)

## Verification

- Docker build (slim image): **success** (~7 min cold local build)
- Oracle + pytest in container: **50/50 passed**
- `terminus_zip.py preflight`: **all checks passed**
- Zip: `tasks/pawn-endgame-table-audit.zip` (29 entries, forward slashes)

## Resubmit notes

- Cycle 1: `regenerate_rubric` ON, `Send to Reviewer` OFF — paste updated `rubrics.txt`
- Cycle 2: `regenerate_rubric` OFF, `Send to Reviewer` ON

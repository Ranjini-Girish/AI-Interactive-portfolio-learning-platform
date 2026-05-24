# Revision fixes — 5b3b84d0-fea4-48ae-ae03-3e670f3cabec

## Wave 1 hardening (resolved)

- [x] Confirm `solution/solve.sh`, `tests/test.sh`, and `environment/Dockerfile` use **LF** line endings (already LF at extract; preserved on edit).
- [x] Add `tmux` and `asciinema` to `environment/Dockerfile` for terminus-2 harness startup.
- [x] Pre-install `pytest==8.4.1` and `pytest-json-ctrf==0.3.5` in Dockerfile (no runtime pip in `solve.sh` or `tests/test.sh`).
- [x] Add `python` → `python3` symlink in Dockerfile for harness compatibility.
- [x] Add `ensure_files` EXIT trap to `tests/test.sh` (Doc-06 crash-safety).
- [x] Leakage grep clean (`instruction.md`, `tests/test_outputs.py`, `SPEC.md`, `rubrics.txt`).

## Verification

- `terminus_zip.py preflight`: **All checks passed** (ruff, leakage, env file count 28/small, tmux+asciinema, test.sh shape).
- Local oracle + pytest: **20/20 passed**.

## Portal status at revision prep (2026-05-23)

- Wave 1 revision prep only — E2E submit not run from this pass.

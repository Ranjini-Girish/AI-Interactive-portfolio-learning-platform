# Revision fixes — b0907c07-03af-45c7-8136-028704d18838

## Portal feedback (resolved)

- [x] AutoEval build FAILED / oracle failed — normalize `solution/solve.sh`, `tests/test.sh`, and `environment/Dockerfile` to **LF** line endings (CRLF caused `pipefail\r` / bad interpreter on Linux).
- [x] Remove stray `# DNS alias chain solver` copy-paste block from `solution/solve.sh`.
- [x] Add `python` → `python3` symlink in Dockerfile for harness compatibility.

## Verification

- Local oracle + pytest: **10/10 passed** after LF fix.

## Portal status at extract (2026-05-23)

- AutoEval: build FAILED; oracle skipped.
- Quality checks: pass.
- No human reviewer prose (AutoEval-only revision).

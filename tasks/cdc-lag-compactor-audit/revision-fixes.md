# Revision fixes — 2fd03871-d392-44a6-b133-00c9bb542cd5

## Wave 1 hardening (2026-05-23)

- [x] CRLF→LF on `solution/solve.sh`, `tests/test.sh`, and `environment/Dockerfile`.
- [x] Pre-install `tmux`, `asciinema`, `python3`, `pytest==8.4.1`, and `pytest-json-ctrf==0.3.5` in Dockerfile (`allow_internet = false` offline verifier).
- [x] Replace runtime `curl`/`uvx` bootstrap in `tests/test.sh` with direct `python -m pytest`.
- [x] Add `python` → `python3` symlink in Dockerfile.
- [x] Oracle: copy inline Rust reference into `/app/auditor/src/main.rs` before building `/app/bin/cdc-audit` (verifier checks authored sources).
- [x] Leakage grep clean on reviewer-visible files.

- [x] Refresh stale `EXPECTED_INPUT_HASH` in `tests/test_outputs.py` to match current `/app/cdc` fixtures.

## Verification

- Preflight: **PASS** (ruff clean, leakage clean, env file count 25 = `small`, tmux/asciinema present, offline `test.sh`).
- Local oracle + pytest (Docker): **12/12 passed**, `reward.txt = 1`.

## Portal status at extract (2026-05-23)

- UUID: `2fd03871-d392-44a6-b133-00c9bb542cd5`
- Wave 1 revision prep only — no E2E platform submit in this pass.

# Revision fixes — 8d198124-d872-4df6-9ef7-3d03eac93ddd

## Wave 1 hardening (2026-05-23)

- [x] CRLF→LF on `solution/solve.sh`, `tests/test.sh`, and `environment/Dockerfile` (already LF; re-verified after edits).
- [x] Pre-install `tmux`, `asciinema`, `python3`, `pytest==8.4.1`, and `pytest-json-ctrf==0.3.5` in Dockerfile (`allow_internet = false` offline verifier).
- [x] Replace runtime `python3 -m pytest` with canonical `python -m pytest` in `tests/test.sh`; add `ensure_files` EXIT trap for crash-safety.
- [x] Add `python` → `python3` symlink in Dockerfile.
- [x] `solution/solve.sh` — no runtime `pip`/`curl`/`apt-get` (already clean).
- [x] Leakage grep clean on reviewer-visible files (`instruction.md`, `tests/test_outputs.py`, `environment/ledger_epoch/SPEC.md`, `rubrics.txt`).

## Verification

- Preflight: **PASS** — ruff clean, leakage OK, env file count 24 (`small`), tmux/asciinema present, test.sh reward section OK.
- Local oracle + pytest: **14/14 passed** (Go build + `LES_*` env vars + `pytest tests/test_outputs.py -q`).

## Portal status at extract (2026-05-23)

- UUID: `8d198124-d872-4df6-9ef7-3d03eac93ddd`
- Wave 1 revision prep only — no E2E platform submit in this pass.

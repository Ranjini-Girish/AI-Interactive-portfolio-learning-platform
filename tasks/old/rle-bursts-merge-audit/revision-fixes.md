# Revision fixes — e0705c3d-623e-4701-823f-4fd683c8a48a

## Wave 1 hardening (2026-05-23)

- [x] CRLF→LF on `solution/solve.sh`, `tests/test.sh`, and `environment/Dockerfile` (already LF; normalization script confirmed).
- [x] Pre-install `tmux`, `asciinema`, `pytest==8.4.1`, and `pytest-json-ctrf==0.3.5` in Dockerfile (`allow_internet = false` offline verifier).
- [x] `tests/test.sh` uses direct `python -m pytest` with canonical reward block (no runtime `curl`/`uvx`/`pip install`).
- [x] Add defensive `python` → `python3` symlink in Dockerfile.
- [x] `solution/solve.sh` has no runtime `pip`/`apt`/`curl`; no stray copy-paste comments.
- [x] Leakage grep clean on reviewer-visible files (`solve.sh`, `solution/`, `/solution`, `/sol`, `oracle`).

## Verification

### Preflight (`terminus_zip.py preflight`)

```
All checks passed!
preflight: ruff ... OK
leak-check: OK
preflight: environment file count (excl Dockerfile/docker-compose) = 25
preflight: task.toml codebase_size = 'small'
preflight: task.toml [environment] required fields OK (workdir + allow_internet)
preflight: tests/test.sh OK (no forbidden runtime installs; defensive reward write present)
preflight: terminus-2 harness packages OK (tmux + asciinema referenced in environment/Dockerfile)
```

### Local oracle + pytest

- Oracle: `python solution/audit.py` with `RBM_DATA_DIR=environment/rbm_lat`, `RBM_AUDIT_DIR=local-audit`
- Pytest: **3 passed / 3 total** (`tests/test_outputs.py -q`)

## File changes this pass

| File | Change |
|---|---|
| `environment/Dockerfile` | Added `ln -sf /usr/local/bin/python3 /usr/local/bin/python` after pip install |

No other files required edits; task was already compliant on offline verifier shape, harness packages, and leakage policy.

## Portal status at extract (2026-05-23)

- UUID: `e0705c3d-623e-4701-823f-4fd683c8a48a`
- Wave 1 revision prep only — no E2E platform submit in this pass.
- Agent trials (GPT-5.2 / Opus 4.6) not run locally; required before final send.

## Issues needing portal feedback (none blocking Wave 1)

- `task.toml` declares `workdir = "/app"` with `number_of_milestones = 0`; edition-2 guidance prefers omitting `workdir` on non-milestone tasks, but preflight accepts the current shape.
- `tests/test_outputs.py` has only 3 hash-locked tests; confirm bundled dataset still exercises every enum/diagnostic in `SPEC.md` before resubmit if reviewer flagged coverage gaps.
- Solvability evidence (≥1 GPT-5.2 and ≥1 Opus 4.6 trial) must be collected on platform before human review send.

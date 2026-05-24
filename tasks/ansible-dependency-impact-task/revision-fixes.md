# Revision fixes — ea5f4223-d084-436e-9a54-8acb7fa45f3f

## Reviewer feedback (resolved)

- [x] Remove runtime `pip3 install PyYAML==6.0.1` from `solution/solve.sh` (redundant; violates offline oracle under `allow_internet = false`).

## Preflight / CI (resolved)

- [x] Remove `# scaffold-status: oracle-pending` from `tests/test_outputs.py` (leakage grep).

## Rubric notes (no action this cycle)

- Validator false positive on max cumulative score (positives sum to 20).
- Prefer positive-form penalty phrasing on future tasks.

## Portal status at extract (2026-05-23)

- Difficulty: HARD; Opus 80% (4/5), GPT-5.2 0% (0/5) — acceptable hard band.
- Quality checks: pass.
- Oracle: 100% (3/3) after fix.

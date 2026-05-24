# Revision fixes — c12f5c5c-1896-471d-a039-601ff5ac2fba

## Portal feedback

- **Reason:** `autoeval_build_failed` — CodeBuild `CodeExecutionEnvironment:959310a9-52af-499f-9b36-faca2ccdc918` (5/22 zip).
- **Prior reviewer note (ea5f4223):** runtime `pip3 install PyYAML` in `solution/solve.sh` under `allow_internet = false`.

## Root cause

The 5/22 submission still carried build/oracle blockers that are now fixed in-tree:

1. **`solution/solve.sh`** — removed runtime `pip3 install PyYAML==6.0.1`; PyYAML is preinstalled in `environment/Dockerfile`.
2. **`tests/test_outputs.py`** — removed `# scaffold-status: oracle-pending` (leakage grep token).
3. **`environment/Dockerfile`** — added `tmux` + `asciinema`; preinstalls `pytest==8.4.1`, `pytest-json-ctrf==0.3.5`, `PyYAML==6.0.1`.
4. **`tests/test.sh`** — offline pytest wrapper with canonical `$?` reward suffix and Doc-06 crash-safety writes.
5. **`task.toml`** — `allow_internet = false`, `workdir = "/app"`, `codebase_size = "small"` (53 env files).

## Changes this prep cycle

| File | Change |
|------|--------|
| `environment/Dockerfile` | Pin `python:3.13-slim-bookworm` to repo-canonical digest `f41a75c9…` (replaces stale `8bc60ca0…` that resolved to trixie apt indexes locally). |

## Verification (2026-05-24)

```text
python tools/terminus-task-tools/terminus_zip.py preflight tasks/ansible-dependency-impact-task  → PASS
python tools/terminus-task-tools/terminus_zip.py clean tasks/ansible-dependency-impact-task    → OK
python tools/terminus-task-tools/terminus_zip.py build tasks/ansible-dependency-impact-task    → 60 entries
python tools/terminus-task-tools/terminus_zip.py verify-task tasks/ansible-dependency-impact-task → OK
```

- Ruff: clean
- Leakage grep: clean (instruction.md, tests/test_outputs.py)
- Docker smoke (prior image): `tmux`, `asciinema`, PyYAML 6.0.1 on PATH
- No dev artifacts (`local-audit`, `__pycache__`, `.pytest_cache`) present

## Resubmit notes

- **Do not** include `rubrics.txt` in the zip (build tool already excludes it).
- `revision-fixes.md` is local-only documentation; safe to omit from upload if manually zipping.
- Fast static checks on 5/24 resubmit already reported **Build SUCCEEDED** (`CodeExecutionEnvironment:7f57b2ae…`) with this task content; re-upload the freshly built zip after digest pin.
- Difficulty remains **HARD**; agent solvability (0/5 on both models) is acceptable for hard band — not a build blocker.

## Deep-dive (2026-05-24) — why it kept bouncing

### 1. Original blocker (fixed)

5/22 zip: runtime `pip install PyYAML` in `solve.sh` + missing harness deps → **Build FAILED**.

Local verify now: Docker build OK, oracle **49/49** pytest.

### 2. Last E2E submit (08:12 UTC) — build actually passed

Fast static check at click time reported:

- **AutoEval Build SUCCEEDED** (`CodeExecutionEnvironment:c7c79476…`)
- **Difficulty: HARD** (Opus 20%, GPT 0%)
- **Quality checks: pass**
- **Status: ❌ Some tests not passed by any agent run**

Platform UI: *“Send to reviewer only if difficulty and quality checks are passing — otherwise it will always result in revision.”* The **solvability status line** (not the HARD band) is the likely auto-revision trigger on full CodeBuild even when build succeeds.

Stale **Reviewer Feedback** banner still shows the old 5/22 **Build FAILED** (`a284d0cd…`); ignore that header — it is not the latest eval.

### 3. Zip hygiene bug (fixed this pass)

`revision-fixes.md` was **included in the submission zip** (60 entries). It contains `oracle`, `solution/solve.sh`, and `/solution` — leakage tokens. Local preflight only greps `instruction.md` + `tests/test_outputs.py`; platform may scan the whole archive.

**Fix:** add `revision-fixes.md` to `terminus_zip.py` `SKIP_FILE_NAMES`; rebuild zip (59 entries).

### 4. Portal state (now)

`c12f5c5c…` is **not** in the 0490 revision queue (11 other cards visible). After 08:12 submit it left the queue → likely **Evaluation pending** or awaiting full CodeBuild cycle, not an open Revise card.

## Remaining blockers

- Confirm full CodeBuild (not just fast static) shows Build SUCCEEDED + solvability pass.
- If solvability status stays ❌, download difficulty-check artifact and identify which pytest nodes never pass on any agent run (GPT 0/5 may leave gaps even when Opus 1/5 passes fully).

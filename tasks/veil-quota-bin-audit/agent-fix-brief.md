# Agent fix brief — veil-quota-bin-audit

Generated from revision extraction (`api+scrape`).
**Fix in place, then run upload phase. Do not submit until preflight passes.**

## Identifiers

| Field | Value |
|-------|-------|
| revisionTaskId | `021f9c95-f7c9-4d2f-b684-796382447238` |
| assignmentId | `db76db63-230e-40e2-8e8e-050f22a9e3b4` |
| task directory | `tasks/veil-quota-bin-audit` |

## Signals

| Signal | Value |
|--------|-------|
| evaluationOutcome | NEEDS_REVISION |
| difficultyBand | hard |
| solvable | false |

### Agent stats
- nop: 0% (0/1)
- oracle: 100% (3/3)
- terminus-gpt5-2: 0% (0/5)
- terminus-claude-opus-4-6: 0% (0/5)

### revisionReasons
- `agents_unsolvable`
- `platform_needs_revision`
- `autoeval_build_failed`

## Fix guidance

- **agents_unsolvable**: Fix instruction/SPEC gaps so every pytest node passes on at least one agent run.
- **platform_needs_revision**: Ensure build + difficulty + quality pass before Send to reviewer.
- **autoeval_build_failed**: Confirm slim Dockerfile, offline test.sh, tmux/asciinema, no runtime pip in solve.sh. Run terminus_zip.py preflight + docker oracle.

## Human reviewer

(none)

## QC failures

❌ fail - behavior_in_tests: The masking step is described in both instruction.md and SPEC.md ("applies masks", "union zero_slots per sample_id before arithmetic"), but it is never actually exercised by the test data. incident_log.json uses sample IDs "sbr_04" and "sbr_09", while every sample file uses the "vqb_" prefix (vqb_00 through vqb_11). No mask ever matches any sample, so the masking code path produces the same result as if masking were skipped entirely. An agent that omits mask application entirely would still produce the correct canonical hashes and pass all tests, meaning a key pipeline step goes unverified.
❌ fail - structured_data_schema: SPEC.md documents summary.json completely (all keys listed). However, for veil_bins.json the schema section only says "Top-level samples object listing every sample id from sorted sample_*.json files" without defining what each sample's value looks like. The per-sample histogram entry structure—a list of objects with "bin" (integer) and "tally" (integer) keys—is only inferable from algorithm terminology scattered through the pipeline description ("tally at the smallest bin key", "Emit positive tallies sorted by bin"). There is no explicit, normative definition of the histogram-row object schema in either instruction.md or SPEC.md.

## Difficulty summary

Difficulty: ✅ HARD

Status: ❌ Some tests not passed by any agent run

Agent Performance:
  • terminus-claude-opus-4-6: 0.0% (0/5 runs)
  • terminus-gpt5-2: 0.0% (0/5 runs)

Reference Agents:
  • nop: 0.0% (0/1 runs)
  • oracle: 100.0% (3/3 runs)

Failure Breakdown:
  • nop: 1 other
  • terminus-claude-opus-4-6: 5 other
  • terminus-gpt5-2: 2 timeout(s), 3 other

Agent Timeout Gate: ✅ 2/10 real-agent runs timed out (<5; not blocking by itself)

Unit Tests Results:
  • TestInputIntegrity → test_each_input_file_sha256: 10 passed / 10 runs
  • TestPolicyFlags → test_veil_spill_enabled_in_summary: 8 passed / 10 runs
  • TestPolicyFlags → test_veil_cap_recorded: 8 passed / 10 runs
  • TestVeilBins → test_samples_object_covers_every_fixture_id: 8 passed / 10 runs
  • TestReportStructure → test_output_canonical_hashes: 0 passed / 10 runs
  • TestReportStructure → test_field_hashes: 0 passed / 10 runs
  • TestVeilBins → test_histogram_rows_sorted_by_bin: 4 passed / 10 runs

Analysis on Agent Failures:
  • Task Instruction Sufficiency: ❌ FAIL, ## Job Summary

### 1. Overall Results

**0/10 trials passed** (reward = 0.0 for all). No trials achieved a passing reward. Test pass rates varied:
- **5/7 tests**: tbench-task__3dP4o4q, tbench-task__4xyNVou, tbench-task__oGawdEN, tbench-task__fZeLR4V
- **4/7 tests**: tbench-task__Lp7UuWG, tbench-task__7tmvMHA, tbench-task__dkvz3to, tbench-task__N5FcqjN
- **1/7 tests**: tbench-task__2tTRjiz, tbench-task__R8aSWVj (terminal freeze — no output produced)

---

### 2. Common Failure Patterns

Three distinct failure modes, affecting nearly every trial:

**A. Missing "latch audit" specification (10/10 trials)** — The most critical and universal failure. SPEC.md references "the same tail hash and assignment counting rules as the latch audit" for `tail_ledger_sha` and `total_assignments`, but no latch audit spec exists anywhere in the environment. Multiple agents explicitly searched for it and confirmed it was absent. The reference rules are:
- `total_assignments` = total count of all readings (not sum of bin tallies)
- `tail_ledger_sha` = SHA-256 of sorted, comma-joined `"{sid}:{final_prefix_sum}"` pairs

Agents made reasonable but wrong guesses: hashing `pool_state.json`, hashing the ledger serial, or hashing raw sample file bytes.

**B. `veil_bins.json` per-sample schema ambiguity (6/10 trials)** — tbench-task__Lp7UuWG, tbench-task__7tmvMHA, tbench-task__dkvz3to, tbench-task__N5FcqjN, tbench-task__2tTRjiz, tbench-task__R8aSWVj. SPEC.md says "Top-level `samples` object listing every sample id" without specifying whether each sample ID maps to a flat list `[{bin, tally}, ...]` or a wrapper object `{"bins": [...]}`. Agents consistently chose the wrapper form; tests expect bare lists. A secondary issue in the same set: agents used `"count"` instead of `"tally"` as the per-bin field name (tbench-task__Lp7UuWG).

**C. Terminal freeze causing complete output failure (2/10 trials)** — tbench-task__2tTRjiz and tbench-task__R8aSWVj. Both agents triggered unrecoverable terminal states:
- tbench-task__2tTRjiz: ran `grep -RIn "latch..." /` (filesystem-wide grep), filling the output buffer
- tbench-task__R8aSWVj: wrote a large Python script via heredoc (`cat > file <<'PY'...PY`), which caused the terminal to freeze

Both agents spent 500+ steps attempting recovery before timing out at 1500 seconds.

---

### 3. Hack Check

**No cheating detected.** All 10 trials received `reward_hacking: pass`. Agents consistently:
- Stayed within `/app/` for writes
- Never accessed `solution/`
- Never wrote to `/logs/verifier/reward.txt`
- Never modified test files

The 4-5 tests that passed in most trials confirm agents did genuine legitimate work.

---

### 4. Systematic Instruction Issues

The `task_specification: fail` check fired on **all 10 trials**, making this a clear systematic problem with the task design:

1. **Undefined external reference** ("latch audit") — The single biggest issue. This is not a hard problem to solve; it simply requires information that isn't provided. Every agent that found the right core pipeline logic still failed because the `tail_ledger_sha` formula is completely non-inferable.

2. **Underspecified output schema** — The `veil_bins.json` samples structure is ambiguous enough that 6/10 agents chose a reasonable-but-wrong interpretation.

3. **Missing field name** — The per-bin count field (`"tally"`) is never named in the spec; agents defaulted to `"count"`.

These are all genuine specification gaps, not agent limitations. The task is effectively unsolvable from the provided materials alone.

---

### 5. Progress: How Close Did Agents Get?

Agents were remarkably close on the core pipeline work. In the 8 trials that produced output:

- **Core pipeline (masking, lane offsets, veil clipping, prefix folding, veil_spill)**: Correctly implemented by essentially all agents
- **Policy flags in `summary.json`**: Correct
- **Sample ID coverage in `veil_bins.json`**: Correct
- **Input integrity**: Correct

The 4–5 passing tests show agents nailed ~70% of the task. The remaining failures trace almost entirely to the two specification gaps above, not to algorithmic misunderstanding. tbench-task__fZeLR4V was the closest: it passed the `veil_bins.json` canonical hash (correct histogram content) and failed only on `tail_ledger_sha`.

---

### 6. Key Differences Between Trials

No model-level differences are identifiable from the summaries (agent/model metadata not provided). The variation is primarily operational:

| Outcome | Trials |
|---|---|
| Best performance (5/7, correct histogram) | 3dP4o4q, 4xyNVou, oGawdEN, fZeLR4V |
| Mid performance (4/7, schema error + hash error) | Lp7UuWG, 7tmvMHA, dkvz3to, N5FcqjN |
| Terminal freeze (1/7, no output) | 2tTRjiz, R8aSWVj |

The terminal-freeze trials lost all pipeline work due to environment interaction issues unrelated to algorithmic capability. The best-performing agents avoided the `{"bins": [...]}` wrapper but all still fai

… [truncated]

## Agent review

================================================================================
                          REVIEW REPORT: tbench-task
================================================================================

Status:        ⚠️ WARNING
Task Location: /root/harbor_tasks/tbench-task

--------------------------------------------------------------------------------
SUMMARY
--------------------------------------------------------------------------------

This task requires implementing a read-only audit pipeline that processes frozen
training telemetry data: applying incident masks, computing lane offsets with
modular reduction, clipping values at a veil cap, folding prefix sums into
histogram bins, and applying a veil_spill subtraction. The solution implements
the full algorithm in an inline Python script reading JSON fixtures and emitting
two canonical JSON outputs. The test suite uses SHA-256 hash comparisons to
verify exact output correctness, plus structural and semantic checks on the
histogram artifacts.

================================================================================
                              WARNINGS ⚠️
================================================================================

--------------------------------------------------------------------------------
1. Test Dependencies Installed in Dockerfile
--------------------------------------------------------------------------------

File:    tbench-task/environment/Dockerfile (lines 12-14)
Problem: pytest and pytest-json-ctrf are test-only dependencies installed in
         the Docker image. These should be installed in test.sh instead, keeping
         the agent environment free of verifier tooling.

Current code:
┌─────────────────────────────────────────────────────────────────────────────┐
│  RUN python -m pip install --no-cache-dir \                                 │
│      pytest==8.4.1 \                                                        │
│      pytest-json-ctrf==0.3.5                                                │
└─────────────────────────────────────────────────────────────────────────────┘

Suggested fix:
┌─────────────────────────────────────────────────────────────────────────────┐
│  # Remove from Dockerfile; install in tests/test.sh instead:                │
│  pip install pytest==8.4.1 pytest-json-ctrf==0.3.5                          │
└─────────────────────────────────────────────────────────────────────────────┘

Explanation: Test dependencies should live in test.sh so the agent image stays
clean. The current test.sh skips installation because it relies on the
Dockerfile—this couples the verifier to the build image unnecessarily and
exposes pytest to the agent during execution.

--------------------------------------------------------------------------------
2. Incorrect Task Category
--------------------------------------------------------------------------------

File:    tbench-task/task.toml (line 6)
Problem: Category is "machine-learning" but the task involves no model training,
         inference, or evaluation. It is a deterministic data transformation and
         audit pipeline operating on JSON fixtures.

Current approach: `category = "machine-learning"`

Suggested fix:
┌─────────────────────────────────────────────────────────────────────────────┐
│  category = "data-processing"                                               │
└─────────────────────────────────────────────────────────────────────────────┘

Explanation: The task reads JSON data, applies arithmetic transformations
(masking, modular offsets, clipping, prefix folding), and emits structured
output. This maps cleanly to "data-processing." The tag "gradient-clip" is
misleading—the operation is veil clipping, not ML gradient clipping.

================================================================================
                             SUGGESTIONS 💡
================================================================================

----------

… [truncated]

## Test quality

================================================================================
                      TEST QUALITY REVIEW: tbench-task
================================================================================

Status:    ✅ ROBUST
Severity:  Minor

================================================================================
                         OVERALL ASSESSMENT
================================================================================

Recommendation: ACCEPT
The test suite uses SHA-256 hash verification of both output files' logical
content, which cryptographically locks the exact correct values and prevents
any shortcut solution; only minor formatting verification is absent.

Strengths:  Cryptographic hash checks on full output content make it
impossible to pass without correctly implementing the multi-step algorithm.
Input integrity hashes also ensure the agent does not tamper with source data.

Weaknesses: The SPEC-mandated canonical JSON format (two-space indent,
trailing newline) is not verified on disk, and incident_log masks happen
to match no sample in the fixture set, leaving that code path unexercised.

================================================================================
                                 SUMMARY
================================================================================

The test suite contains six distinct test methods spanning input integrity,
output correctness (via SHA-256 hashes of canonicalized content), field-level
hash pinning, policy flag checks, sample coverage, and bin sort order. The
SHA-256 locks on both veil_bins.json and summary.json are the critical
assertion: they verify the exact logical content of every computed value,
making brute-force or shortcut approaches infeasible. The only gaps are
the on-disk formatting requirement and the non-exercised mask application
path, both of which are secondary concerns.

================================================================================
                         OTHER OBSERVATIONS 💡
================================================================================

--------------------------------------------------------------------------------
1. Canonical JSON on-disk format not verified
--------------------------------------------------------------------------------

Where:   tests/test_outputs.py:98-103
Problem: The SPEC mandates "two-space indent, sorted keys, ASCII, single
trailing newline" for output files. However, test_output_canonical_hashes
loads the file as JSON, then re-serializes with compact separators before
hashing. An agent could emit compact one-line JSON and still pass.

Current test:
┌─────────────────────────────────────────────────────────────────────────────┐
│  canon = _canonical(outputs[name])  # uses separators=(",",":")             │
│  digest = _sha256_bytes(canon.encode("utf-8"))                              │
│  assert digest == expected                                                  │
└─────────────────────────────────────────────────────────────────────────────┘

Required fix:
┌─────────────────────────────────────────────────────────────────────────────┐
│  raw = (AUDIT_DIR / name).read_bytes()                                      │
│  assert raw == (json.dumps(outputs[name], indent=2, sort_keys=True,         │
│                  ensure_ascii=True) + "\n").encode("utf-8")                  │
└─────────────────────────────────────────────────────────────────────────────┘

Explanation: This is a secondary constraint. An agent that outputs valid JSON
with correct values but wrong formatting (e.g., no indentation) will still
pass every test. The practical impact is low since the core computation
is still fully verified.

--------------------------------------------------------------------------------
2. Incident-log mask path never exercised by fixture data
--------------------------------------------------------------------------------

Where:   environment/vqb_lab

… [truncated]

## Agent checklist

1. Edit `tasks/veil-quota-bin-audit/` — follow terminus-project.mdc (no leakage, offline verifier).
2. `python tools/terminus-task-tools/terminus_zip.py preflight tasks/veil-quota-bin-audit`
3. Update `tasks/veil-quota-bin-audit/revision-fixes.md`
4. Upload: `SNORKEL_REVISION_UPLOAD_ONLY=1 SNORKEL_REVISION_TASK_ID=021f9c95-f7c9-4d2f-b684-796382447238 SNORKEL_UPLOAD_TASK_DIR=tasks/veil-quota-bin-audit` then `npm run flow:revision:upload`

Source: `e2e/audit/revision-021f9c95-f7c9-4d2f-b684-796382447238-context.json`

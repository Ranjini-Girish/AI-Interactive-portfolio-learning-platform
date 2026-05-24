# Agent fix brief — ribbon-winding-quorum-audit

Generated from revision extraction (`api+scrape`).
**Fix in place, then run upload phase. Do not submit until preflight passes.**

## Identifiers

| Field | Value |
|-------|-------|
| revisionTaskId | `c0f4de24-3ef0-447e-a93a-311e67b21bb4` |
| assignmentId | `2a3a62d8-aff8-4c1f-8164-9883b798aad4` |
| task directory | `tasks/ribbon-winding-quorum-audit` |

## Signals

| Signal | Value |
|--------|-------|
| evaluationOutcome | NEEDS_REVISION |
| difficultyBand | trivial |
| solvable | true |

### Agent stats
- nop: 0% (0/1)
- oracle: 100% (3/3)
- terminus-gpt5-2: 100% (5/5)
- terminus-claude-opus-4-6: 100% (5/5)

### revisionReasons
- `difficulty_trivial`
- `platform_needs_revision`
- `autoeval_build_failed`
- `difficulty_below_medium`

## Fix guidance

- **difficulty_trivial**: TRIVIAL band — add interacting algorithmic twists (compound rules, multi-phase pipeline). Do not strip SPEC.
- **platform_needs_revision**: Ensure build + difficulty + quality pass before Send to reviewer.
- **autoeval_build_failed**: Confirm slim Dockerfile, offline test.sh, tmux/asciinema, no runtime pip in solve.sh. Run terminus_zip.py preflight + docker oracle.
- **difficulty_below_medium**: Harden difficulty with additional interacting rules.

## Human reviewer

(none)

## QC failures

❌ fail - behavior_in_tests: instruction.md explicitly requires 'ASCII-only text, two-space indentation, recursively sorted object keys at every object level, no stray trailing spaces on lines, and exactly one trailing newline at EOF.' The tests verify only the canonical minified JSON hash (json.dumps with sort_keys=True and no indent), which confirms data values and key presence but does not check the actual file presentation: 2-space indentation, absence of trailing spaces, and the single trailing newline are untested. Additionally, the requirement to never modify files under the read root and the binary location/name are not tested.

## Difficulty summary

Difficulty: ❌ TRIVIAL - Requires at least MEDIUM

Status: ✅ Solvable (all tests passed by at least one agent run)

Agent Performance:
  • terminus-claude-opus-4-6: 100.0% (5/5 runs)
  • terminus-gpt5-2: 100.0% (5/5 runs)

Reference Agents:
  • nop: 0.0% (0/1 runs)
  • oracle: 100.0% (3/3 runs)

Failure Breakdown:
  • nop: 1 other

Unit Tests Results:
  • TestInputIntegrity → test_each_input_file_sha256: 10 passed / 10 runs
  • TestReportStructure → test_output_canonical_hashes: 10 passed / 10 runs
  • TestReportStructure → test_nested_field_hashes: 10 passed / 10 runs
  • TestCrisisAndSummary → test_crisis_latches_on_severity_day: 10 passed / 10 runs
  • TestCrisisAndSummary → test_summary_counts: 10 passed / 10 runs
  • TestSegmentStatuses → test_status_examples_present: 10 passed / 10 runs
  • TestIncidentTrail → test_applied_follows_day_then_event_id: 10 passed / 10 runs
  • TestLaneRollups → test_west_lane_ok_and_short_split: 10 passed / 10 runs
  • TestLaneRollups → test_north_lane_frozen_bucket: 10 passed / 10 runs

Analysis on Agent Failures:
  • Task Instruction Sufficiency: ➖ NOT_APPLICABLE, debug output not available

## Agent review

================================================================================
                         REVIEW REPORT: tbench-task
================================================================================

Status:        ⚠️ WARNING
Task Location: /root/harbor_tasks/tbench-task

--------------------------------------------------------------------------------
SUMMARY
--------------------------------------------------------------------------------

This task requires implementing a deterministic "ribbon winding quorum audit"
tool in Go 1.23 that reads a frozen lab dataset of ribbon segments, anchor
masks, pool ballots, and day-stamped lane incidents, replays incident effects,
evaluates per-segment quorum status, and writes four canonical JSON files. The
solution is a 389-line Go program that correctly implements the full spec. The
test suite uses SHA-256 hash-locks on all inputs and outputs for exact
correctness, supplemented by semantic checks on crisis state, segment statuses,
incident ordering, and lane rollups.

================================================================================
                              WARNINGS ⚠️
================================================================================

--------------------------------------------------------------------------------
1. Test Dependencies Installed in Dockerfile
--------------------------------------------------------------------------------

File:    tbench-task/environment/Dockerfile (lines 16-18)
Problem: pytest and pytest-json-ctrf are test-only dependencies installed in
         the container image. These should be installed in tests/test.sh
         instead, per Terminal-Bench best practices. The agent (building a Go
         binary) has no use for pytest.

Current code:
┌─────────────────────────────────────────────────────────────────────────────┐
│  && python3 -m pip install --no-cache-dir --break-system-packages \         │
│      pytest==8.4.1 \                                                        │
│      pytest-json-ctrf==0.3.5 \                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Suggested fix: Remove the pip install lines from the Dockerfile and install
these dependencies in tests/test.sh instead:
┌─────────────────────────────────────────────────────────────────────────────┐
│  # In tests/test.sh, before running pytest:                                 │
│  pip install --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5           │
└─────────────────────────────────────────────────────────────────────────────┘

Explanation: Test dependencies should not be in the agent's image. While the
current approach works, it exposes test framework packages to the agent
unnecessarily and conflates environment setup with verifier setup.

================================================================================
                             SUGGESTIONS 💡
================================================================================

--------------------------------------------------------------------------------
1. Unnecessary Packages in Dockerfile
--------------------------------------------------------------------------------

File:    tbench-task/environment/Dockerfile (lines 9-10)

Current approach: The Dockerfile installs `asciinema` and `tmux`, which are
unrelated to building Go binaries or processing JSON data.

Suggested improvement:
┌─────────────────────────────────────────────────────────────────────────────┐
│  RUN apt-get update \                                                       │
│      && apt-get install -y --no-install-recommends \                         │
│          ca-certificates \                                                   │
│          golang-go \                                                         │
│          python3 \                                                           │
│          python3-pip \               

… [truncated]

## Test quality

================================================================================
                      TEST QUALITY REVIEW: tbench-task
================================================================================

Status:    ⚠️  VULNERABLE
Severity:  Major

================================================================================
                         OVERALL ASSESSMENT
================================================================================

Recommendation: STRENGTHEN
The test suite cryptographically verifies computational correctness of all
four output files but completely ignores the explicit Go implementation
requirement, allowing an agent to pass using Python alone.

Strengths:  SHA-256 hash locks on canonical output JSON make it impossible to
pass without computing byte-perfect correct values for all four audit files.
Input integrity checks, semantic spot-checks, and field-level nested hashes
provide defence in depth on the algorithmic outputs.

Weaknesses: No test verifies the existence of Go source code, go.mod, or the
rwqaudit binary. No test verifies the on-disk JSON formatting requirements
(two-space indent, trailing newline). An agent can implement the entire
algorithm in Python (which is pre-installed in the container) and pass every
test.

================================================================================
                                 SUMMARY
================================================================================

The test suite contains 8 test methods across 6 classes. The crown jewel is
test_output_canonical_hashes which SHA-256-locks all four output files via
their minified canonical JSON, making it effectively impossible to pass
without implementing the full quorum audit algorithm correctly. However, the
instruction explicitly requires a Go 1.23 implementation with go.mod and a
compiled rwqaudit binary, yet no test checks for their existence. Since
Python 3 is installed in the agent container, the agent can write a ~100-line
Python script, produce the correct outputs, and satisfy every assertion.

================================================================================
                            CRITICAL GAPS ❌
================================================================================

--------------------------------------------------------------------------------
1. Go implementation requirement is entirely untested
--------------------------------------------------------------------------------

Where:   tests/test_outputs.py (entire file)
Problem: The instruction mandates "Implement the audit in Go 1.23 with
go.mod and sources under /app/rwq_tool/, build a single rwqaudit binary in
that directory." No test checks that /app/rwq_tool/go.mod exists, that Go
source files exist, or that a compiled binary /app/rwq_tool/rwqaudit is
present.

Current test:
┌─────────────────────────────────────────────────────────────────────────────┐
│  (no test exists)                                                           │
└─────────────────────────────────────────────────────────────────────────────┘

Required fix:
┌─────────────────────────────────────────────────────────────────────────────┐
│  def test_go_binary_exists():                                               │
│      binary = Path("/app/rwq_tool/rwqaudit")                                │
│      assert binary.is_file(), "compiled rwqaudit binary not found"          │
│      assert os.access(binary, os.X_OK), "binary is not executable"         │
│                                                                             │
│  def test_go_mod_exists():                                                  │
│      mod = Path("/app/rwq_tool/go.mod")                                     │
│      assert mod.is_file(), "go.mod not found"                               │
│      content = mod.read_text()                                              │
│      assert "module" in content                             

… [truncated]

## Agent checklist

1. Edit `tasks/ribbon-winding-quorum-audit/` — follow terminus-project.mdc (no leakage, offline verifier).
2. `python tools/terminus-task-tools/terminus_zip.py preflight tasks/ribbon-winding-quorum-audit`
3. Update `tasks/ribbon-winding-quorum-audit/revision-fixes.md`
4. Upload: `SNORKEL_REVISION_UPLOAD_ONLY=1 SNORKEL_REVISION_TASK_ID=c0f4de24-3ef0-447e-a93a-311e67b21bb4 SNORKEL_UPLOAD_TASK_DIR=tasks/ribbon-winding-quorum-audit` then `npm run flow:revision:upload`

Source: `e2e/audit/revision-c0f4de24-3ef0-447e-a93a-311e67b21bb4-context.json`

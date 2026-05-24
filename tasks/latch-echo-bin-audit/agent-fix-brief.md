# Agent fix brief — latch-echo-bin-audit

Generated from revision extraction (`unknown`).
**Fix in place, then run upload phase. Do not submit until preflight passes.**

## Identifiers

| Field | Value |
|-------|-------|
| revisionTaskId | `9c8fef7e-cac5-4076-a8b8-c5e1fe8c2235` |
| assignmentId | `e2416453-41d2-4545-ba40-e5b2a7713662` |
| task directory | `tasks/latch-echo-bin-audit` |

## Signals

| Signal | Value |
|--------|-------|
| evaluationOutcome | unknown |
| difficultyBand | unknown |
| solvable | unknown |

### Agent stats
(none)

### revisionReasons
- `reviewer_feedback_present`

## Fix guidance

- **reviewer_feedback_present**: Review context JSON.

## Human reviewer

Reviewer Feedback
This latch-bin audit task is clear, but the verifier is too tied to the shipped fixture files. Most of the main checks compare fixed hashes for the current input and output files, so a solution could pass by matching this exact dataset instead of proving the latch pipeline works generally. Since the instruction supports LEB_DATA_DIR and LEB_AUDIT_DIR, add at least one alternate/generated fixture test to confirm the logic works outside the bundled data. Also, pytest and pytest-json-ctrf are installed in the Docker image even though they are verifier tools, so move them into the verifier setup or clearly justify the offline preload.
Do you disagree with the reviewer feedback?
Questions to answer
All form questions are required unless marked as optional.
Terminal bench 2.0 task submission
Upload terminal bench 2.0 submission here (zip file)

Zip file should have all files in the root, not under any folder.

Upload terminal bench 2.0 submission here (zip file) *
latch-echo-bin-audit.zip
5/22/2026, 5:11:59 PM
Fast static checks

Run quick static checks to verify submission structure and files. Submit runs slower checks and agent runs and may take a couple of minutes before returning results.

Check feedback
Summary (optional)

Summary of difficulty check - contains results of agent simulation and stats for each test as well as instruction sufficiency check.

Language:
Python
Python
Go
SQL (Snowflake)
JavaScript
TypeScript
Summary
Wrap
Expand
1
2
3
4
5
6
Difficulty: ✅ HARD
Status: ✅ Solvable (all tests passed 
by at least one agent run)
Agent Performance:
  • terminus-claude-opus-4-6: 100.0% 
  (5/5 runs)
Download difficulty check results (optional)

This field will be populated by the system when your code is run by the system.

Download File
Quality check summary (optional)

Please disregard this field if it is blank, during initial submission. This field will be populated by the system when your code is run by the system.

Language:
Python
Python
Go
SQL (Snowflake)
JavaScript
TypeScript
Quality check summary
Wrap
Expand
1
2
## Quality Check Results
✅ pass - 
behavior_in_task_description: 
instruction.md explicitly names both 
output files (latch_bins.json and 
summary.json), states the audit 
directory rules, env-var overrides 
(LEB_DATA_DIR / LEB_AUDIT_DIR), 
Agent review (optional)

Please disregard this field if it is blank, during initial submission. This field will be populated by the system when your code is run by the system.

Languag

## QC failures

(none)

## Difficulty summary

Summary (optional)

Summary of difficulty check - contains results of agent simulation and stats for each test as well as instruction sufficiency check.

Language:
Python
Python
Go
SQL (Snowflake)
JavaScript
TypeScript
Summary
Wrap
Expand
1
2
3
4
5
6
Difficulty: ✅ HARD
Status: ✅ Solvable (all tests passed 
by at least one agent run)
Agent Performance:
  • terminus-claude-opus-4-6: 100.0% 
  (5/5 runs)
Download difficulty check results (optional)

This field will be populated by the system when your code is run by the system.

Download File

## Agent review

Agent review (optional)

Please disregard this field if it is blank, during initial submission. This field will be populated by the system when your code is run by the system.

Language:
Python
Python
Go
SQL (Snowflake)
JavaScript
TypeScript
Agent review
Wrap
Expand
1
2
3
======================================
======================================
====
                          REVIEW 
                          REPORT: 
                          tbench-task
======================================
======================================

## Test quality

Test Quality Report (optional)

Please disregard this field if it is blank, during initial submission. This field will be populated by the system when your code is run by the system.

Language:
Python
Python
Go
SQL (Snowflake)
JavaScript
TypeScript
Test Quality Report
Wrap
Expand
1
2
3
======================================
======================================
====
                      TEST QUALITY 
                      REVIEW: 
                      tbench-task
======================================
======================================

## Agent checklist

1. Edit `tasks/latch-echo-bin-audit/` — follow terminus-project.mdc (no leakage, offline verifier).
2. `python tools/terminus-task-tools/terminus_zip.py preflight tasks/latch-echo-bin-audit`
3. Update `tasks/latch-echo-bin-audit/revision-fixes.md`
4. Upload: `SNORKEL_REVISION_UPLOAD_ONLY=1 SNORKEL_REVISION_TASK_ID=9c8fef7e-cac5-4076-a8b8-c5e1fe8c2235 SNORKEL_UPLOAD_TASK_DIR=tasks/latch-echo-bin-audit` then `npm run flow:revision:upload`

Source: `e2e/audit/revision-9c8fef7e-cac5-4076-a8b8-c5e1fe8c2235-context.json`

# Revision fixes — 2cb6ab3c-8725-4c19-b2da-7d3054c02627

## Root cause of 0% agents / UNSOLVABLE signal

1. **Platform AutoEval build FAILED masked oracle health** — the submitted zip included local revision metadata (`revision-audit.log`, `revision-context.json`) at archive root. Current task tree verifies clean locally (Docker build + `bash solution/solve.sh` + pytest **98/98**), so the failure was likely a bad/stale zip artifact rather than broken oracle logic.
2. **Spec discoverability + input mutation** — the full contract lives in `/app/certs/SPEC.md`, which agents often treat as immutable fixture data and skip. Agents also frequently edit files under `/app/certs/` while prototyping, failing all **35** input SHA-256 gates and yielding reward **0** even when partial output logic is correct.
3. **Ambiguous audit_review tie-break** — `SPEC.md` said “largest list index” without naming `incident_log.events`. The oracle used the filtered `accepted_events` index; agents following the natural reading of the incident log array could diverge on tied `audit_review` rows.
4. **OCSP rollup confusion** — `ocsp_summary.by_state` is leaf-only while `summary.by_ocsp_state` is worst-of-chain. Agents conflate the two tallies and fail hash + semantic summary tests together.

Difficulty band (**HARD**) is appropriate for a Python multi-phase TLS audit; the blocker was solvability infrastructure (build/zip + spec clarity), not “task too easy”.

## Fixes applied

- [x] **Dockerfile** — keep `tmux`/`asciinema`/pytest preinstall; add `python` → `python3` symlink; create `/app/docs/tls_cert_chain_spec.md` symlink to SPEC; **`chmod -R a-w /app/certs`** so input integrity tests survive agent edits.
- [x] **instruction.md** — absolute output path `/app/audit/`; link spec at `/app/docs/tls_cert_chain_spec.md`; state leaf vs worst-of-chain OCSP split (no algorithm hints).
- [x] **SPEC.md** — audit_review tie-break now explicitly “largest array index in `incident_log.events`”.
- [x] **solution/solve.sh** — audit_review winner selection uses original `incident_log.events` indices (aligned with clarified spec); output unchanged on bundled fixtures.
- [x] **tests/test_outputs.py** — updated pinned `SPEC.md` SHA-256 after spec edit.
- [x] **Zip hygiene** — `terminus_zip.py` now skips `revision-audit.log`, `revision-context.json`, `revision-params.json`; removed dev oracle runner before build.

## Verification

| Gate | Result |
|---|---|
| `terminus_zip.py preflight` | **PASS** (ruff, leakage, env count 35/small, harness deps) |
| Local oracle + pytest | **98/98 passed** |
| `terminus_zip.py verify-task` (Docker oracle + pytest) | **PASS** |
| Zip | **41 entries**, flat paths, no revision cruft |

## Zip ready

**Yes** — `tasks/tls-cert-chain-auditor.zip` rebuilt and verified.

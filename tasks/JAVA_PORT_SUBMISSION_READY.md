# Java Port Batch — Submission Ready (2026-05-23)

All **19** tasks: `terminus_zip.py preflight` ✅, flat zip at `tasks/<slug>.zip`, Docker oracle **19/19** green.

**Rubric format** matches [`antireplay-window-audit/rubrics.txt`](antireplay-window-audit/rubrics.txt): each line `Agent …, +/-N` (N ∈ {1,2,3,5}), ≥3 negatives, positives sum 10–40. **Do not zip `rubrics.txt`** — paste into Snorkel platform textbox on **submission cycle 1** (`regenerate_rubric` ON, `Send to Reviewer` OFF), then edit and resubmit cycle 2.

## Submission checklist (each task)

1. Upload `tasks/<slug>.zip` (flat root: `instruction.md`, `task.toml`, `environment/`, `solution/`, `tests/`).
2. Cycle 1: paste rubrics from `tasks/<slug>/rubrics.txt`.
3. Cycle 2: `regenerate_rubric` OFF, `Send to Reviewer` ON.
4. Record harbor trials in `REGISTRY.md`.

---

| # | Task | Zip | Rubrics |
|---|------|-----|---------|
| 1 | systemd-unit-dep-audit | [systemd-unit-dep-audit.zip](systemd-unit-dep-audit.zip) | [rubrics.txt](systemd-unit-dep-audit/rubrics.txt) |
| 2 | git-hook-gate-audit | [git-hook-gate-audit.zip](git-hook-gate-audit.zip) | [rubrics.txt](git-hook-gate-audit/rubrics.txt) |
| 3 | schema-drift-impact-audit | [schema-drift-impact-audit.zip](schema-drift-impact-audit.zip) | [rubrics.txt](schema-drift-impact-audit/rubrics.txt) |
| 4 | k8s-rollout-impact-audit | [k8s-rollout-impact-audit.zip](k8s-rollout-impact-audit.zip) | [rubrics.txt](k8s-rollout-impact-audit/rubrics.txt) |
| 5 | npm-mono-bump-audit | [npm-mono-bump-audit.zip](npm-mono-bump-audit.zip) | [rubrics.txt](npm-mono-bump-audit/rubrics.txt) |
| 6 | cargo-ws-bump-audit | [cargo-ws-bump-audit.zip](cargo-ws-bump-audit.zip) | [rubrics.txt](cargo-ws-bump-audit/rubrics.txt) |
| 7 | pay-ledger-recon-audit | [pay-ledger-recon-audit.zip](pay-ledger-recon-audit.zip) | [rubrics.txt](pay-ledger-recon-audit/rubrics.txt) |
| 8 | crash-sig-triage-audit | [crash-sig-triage-audit.zip](crash-sig-triage-audit.zip) | [rubrics.txt](crash-sig-triage-audit/rubrics.txt) |
| 9 | hitl-queue-consensus-audit | [hitl-queue-consensus-audit.zip](hitl-queue-consensus-audit.zip) | [rubrics.txt](hitl-queue-consensus-audit/rubrics.txt) |
| 10 | ssh-compliance-audit | [ssh-compliance-audit.zip](ssh-compliance-audit.zip) | [rubrics.txt](ssh-compliance-audit/rubrics.txt) |
| 11 | cryostat-lattice-audit | [cryostat-lattice-audit.zip](cryostat-lattice-audit.zip) | [rubrics.txt](cryostat-lattice-audit/rubrics.txt) |
| 12 | stokes-diffusion-audit | [stokes-diffusion-audit.zip](stokes-diffusion-audit.zip) | [rubrics.txt](stokes-diffusion-audit/rubrics.txt) |
| 13 | ledger-event-recon-audit | [ledger-event-recon-audit.zip](ledger-event-recon-audit.zip) | [rubrics.txt](ledger-event-recon-audit/rubrics.txt) |
| 14 | keytab-rotation-audit | [keytab-rotation-audit.zip](keytab-rotation-audit.zip) | [rubrics.txt](keytab-rotation-audit/rubrics.txt) |
| 15 | proc-tree-reaper-audit | [proc-tree-reaper-audit.zip](proc-tree-reaper-audit.zip) | [rubrics.txt](proc-tree-reaper-audit/rubrics.txt) |
| 16 | detector-telem-cal-audit | [detector-telem-cal-audit.zip](detector-telem-cal-audit.zip) | [rubrics.txt](detector-telem-cal-audit/rubrics.txt) |
| 17 | seismic-loc-qc-audit | [seismic-loc-qc-audit.zip](seismic-loc-qc-audit.zip) | [rubrics.txt](seismic-loc-qc-audit/rubrics.txt) |
| 18 | spectral-cal-audit | [spectral-cal-audit.zip](spectral-cal-audit.zip) | [rubrics.txt](spectral-cal-audit/rubrics.txt) |
| 19 | sim-checkpoint-plan-audit | [sim-checkpoint-plan-audit.zip](sim-checkpoint-plan-audit.zip) | [rubrics.txt](sim-checkpoint-plan-audit/rubrics.txt) |

---

## Notes

- **Not included:** `go-race-deadlock-audit` (Go debug task, separate workflow).
- **Large zips:** `stokes-diffusion-audit.zip` (~1.9 MB) — fixture-heavy; others ≤52 KB typical.
- **Re-verify:** `python tools/verify_java_batch_submission.py` or `python tools/docker_verify_java_batch.py`.

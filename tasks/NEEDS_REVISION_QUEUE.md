# NEEDS_REVISION queue — platform vs Girish (Cognyzer tracker)

Last updated: 2026-05-23

Sources:

- **Platform:** Snorkel Experts assignments export (`status: NEEDS_REVISION`, assignee `j26.0479.adl@airdawglabs.com`) — **66** tasks.
- **Cognyzer tracker API:** Girish-filtered tasks, page 1 (`totalCount: 63`, `totalPages: 2`) — page 2 not yet ingested.
- **CSV:** `Project Terminus Task Tracker - Cognyzer - May 1st - 31st.csv` (May export).

Regenerate intersections: `python tools/_girish_union.py`

---

## Summary

| Bucket | Count |
|--------|------:|
| Platform `NEEDS_REVISION` | **66** |
| **Girish** (tracker page 1 ∪ CSV, ∩ platform 66) | **33** |
| **Not Girish** in tracker/CSV | **33** |
| Girish `Needs Revision` in tracker but **not** in platform 66 | **4** |

---

## 1. All 66 platform `NEEDS_REVISION` task IDs

```
02b7c62d-f1f4-4b8e-903e-a0c065b0a57b
093b3435-06d7-47d7-b3d0-445f89b8a06a
115dcd7b-c285-4a4b-8acd-933cddef03d5
14f3a711-4561-431b-a2c7-cd9bcb488392
17431386-697c-4e05-b6f4-2b2dace3d4c8
1c589fb1-3aa2-4a2f-b37c-4d2a6a51c617
1cec7fb5-cbe7-41aa-a633-6a3493b97e4a
23f88a9b-27b3-4f3d-8134-f31f1f2e2fe6
2cb6ab3c-8725-4c19-b2da-7d3054c02627
2fd03871-d392-44a6-b133-00c9bb542cd5
2fdf3090-0206-4a34-9dc2-dce225fd2593
335be3bf-cc8d-4016-8894-5a4b00fc4054
3665a277-0a6b-4ba3-910b-31b8e25af67b
3b3e4434-79b4-4df6-8f7e-db0f7168fd15
3c2c33b8-4177-4cd8-8a87-fa458807f7df
43736316-30a7-4c31-a7da-3d575427ed56
49f2e499-d969-4241-986b-074919b78452
4bd504b7-01e9-42c3-ab9c-604ea0bc9c2e
4c005e09-7d5b-4e9d-acfc-524fa794d003
4c5e54f3-7896-4f5d-a883-a9963e36e106
5b3b84d0-fea4-48ae-ae03-3e670f3cabec
5f2d92cc-7a8f-401c-a397-a4a8f47cf026
6040892f-37a1-47b8-8d7a-3ee68455888c
65a57882-098e-4157-b242-ae5ce58e818a
69ac0fbc-54c6-4119-8688-20c1f860706f
6bdc8901-5d5e-4a3a-ac5f-55aaaee0b21f
6c649f96-8810-46df-91f7-5301bbdbdd38
6d4acddc-3202-4b70-9e61-0b6c32e0bfd8
720485cf-1e8f-4f6d-b5a7-a146b9d1b964
7377e1b7-2c3e-4704-a100-30bc8692accc
7df94103-d243-496b-a314-57e4ec662aef
7eac7bd9-77dd-4c5d-8cd4-f9dcc9bdb407
81d28e74-6395-4fe2-b71e-e6ebdfe5c18c
81e753b5-5d97-4310-9fd5-0db8c378a5c4
82b85d32-18cf-4184-b0cd-f0bbae6e465a
880ff0fc-751e-4495-aeb8-77827cee6ce5
8c8a70e9-c130-48d2-a8ab-c663ce90b874
8d198124-d872-4df6-9ef7-3d03eac93ddd
8fd18659-22ec-4857-aac0-3248ba96b576
91c375bf-3ab3-4fae-b647-c57bd0ce1d79
943ca427-4fb0-4f13-8a48-6379ac6097ff
9ce46c81-d2e4-407a-9b47-a5c035a3f6a3
9ec21e66-f325-4b0f-9ebb-efebd52be30f
a38be328-5193-4de9-8fb9-3b7adc31f5bc
a711d7b8-a9a9-4e40-88e9-95d3272ac3e1
a73c7be3-959d-427c-85e3-1725533b42c0
b03e0244-6eee-46fd-862a-f3e47d44ba1b
b0907c07-03af-45c7-8136-028704d18838
b3cca422-4c7a-4e55-a50f-8df1cb46074e
b65583f8-593b-4915-98a3-227f91d3c047
c0c86689-5c55-47c8-a238-7ad18532a5c9
c6ae9d08-406c-4607-b6dc-0ebc4d6ea170
ce25bed2-7fde-4efb-816b-bbb32ac460c1
d13b444b-40f6-46d9-8632-b89bf88ae7ee
d3cde815-ad94-4ae7-9b17-120d8c8b9f57
d817ff4e-0ec9-4241-bcd2-b7e2ec010764
de430a3a-c0e4-45a5-a9e8-f072d9816e52
e0705c3d-623e-4701-823f-4fd683c8a48a
e7dcbc0a-558d-42c4-acf5-8f8820dae9af
ea5f4223-d084-436e-9a54-8acb7fa45f3f
f2562d6d-b25b-401c-9357-aec84edfb814
f4bf1aec-a79d-4681-a053-971e215eea2d
f6e9d77a-a5fb-478f-b52c-98994b9b50a4
faf82617-f62d-4b79-acfb-4f4e0aa3bce0
fb9cc5df-5d5d-4fe2-bf89-175a4666085c
fea4937d-c7c0-4e6f-862b-604753327459
```

---

## 2. Girish — 33 of 66 (work queue)

These are `NEEDS_REVISION` on the platform **and** attributed to **Girish** in Cognyzer tracker page 1 and/or the May CSV.

| Task ID | Task name (tracker/CSV) | Local folder (`tasks/`) | Source |
|---------|-------------------------|-------------------------|--------|
| `ea5f4223-d084-436e-9a54-8acb7fa45f3f` | ansible-dependency-impact-task | `ansible-dependency-impact-task` | tracker-p1 — **resubmitted 2026-05-23** (reviewer: remove runtime pip from solve.sh) |
| `b0907c07-03af-45c7-8136-028704d18838` | wal-index-trim-audit | `wal-index-trim-audit` | tracker-p1 — **resubmitted 2026-05-23** (CRLF→LF oracle fix) |
| `e0705c3d-623e-4701-823f-4fd683c8a48a` | rle-bursts-merge-audit | `old/rle-bursts-merge-audit` | tracker-p1 — **resubmitted 2026-05-23** |
| `8d198124-d872-4df6-9ef7-3d03eac93ddd` | ledger-epoch-skew-audit | `old/ledger-epoch-skew-audit` | tracker-p1 — **resubmitted 2026-05-23** (tmux/asciinema + test.sh trap) |
| `faf82617-f62d-4b79-acfb-4f4e0aa3bce0` | pawn-endgame-table-audit | `pawn-endgame-table-audit` | tracker-p1 — **resubmitted 2026-05-23** |
| `d13b444b-40f6-46d9-8632-b89bf88ae7ee` | trap-grid-chain-audit | `trap-grid-chain-audit` | tracker-p1 + csv — **resubmitted 2026-05-23** |
| `6d4acddc-3202-4b70-9e61-0b6c32e0bfd8` | slo-burn-window-audit | `slo-burn-window-audit` | tracker-p1 + csv — **resubmitted 2026-05-23** |
| `2fd03871-d392-44a6-b133-00c9bb542cd5` | cdc-lag-compactor-audit | `old/cdc-lag-compactor-audit` | tracker-p1 + csv — **resubmitted 2026-05-23** (offline test.sh + Rust oracle source) |
| `5b3b84d0-fea4-48ae-ae03-3e670f3cabec` | sensor-calib-lattice-audit | `old/sensor-calib-lattice-audit` | tracker-p1 + csv — **resubmitted 2026-05-23** (tmux/asciinema harness) |
| `49f2e499-d969-4241-986b-074919b78452` | stokes-diffusion-audit | `stokes-diffusion-audit` | tracker-p1 + csv — **resubmitted 2026-05-23** (CRLF fix + Go cruft removed) |
| `f4bf1aec-a79d-4681-a053-971e215eea2d` | webhook-retry-ledger-audit | `old/webhook-retry-ledger-audit` | tracker-p1 + csv — **Wave 2 FAIL** (no Revise on 0479 queue) |
| `a711d7b8-a9a9-4e40-88e9-95d3272ac3e1` | replica-lag-window-audit | `replica-lag-window-audit` | tracker-p1 + csv — **resubmitted 2026-05-23** |
| `943ca427-4fb0-4f13-8a48-6379ac6097ff` | replica-lag-window-audit | `replica-lag-window-audit` | csv — **skip duplicate** (same slug as `a711d7b8`) |
| `880ff0fc-751e-4495-aeb8-77827cee6ce5` | train-slot-lattice-audit | `old/train-slot-lattice-audit` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `de430a3a-c0e4-45a5-a9e8-f072d9816e52` | infer-blend-quota-audit | `old/infer-blend-quota-audit` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `2fdf3090-0206-4a34-9dc2-dce225fd2593` | initiative-clash-audit | `old/initiative-clash-audit` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `335be3bf-cc8d-4016-8894-5a4b00fc4054` | patch-slot-lattice-audit | `old/patch-slot-lattice-audit` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `3665a277-0a6b-4ba3-910b-31b8e25af67b` | export-batch-window-audit | `old/export-batch-window-audit` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `c0c86689-5c55-47c8-a238-7ad18532a5c9` | artifact-promote-lattice-audit | `old/artifact-promote-lattice-audit` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `1cec7fb5-cbe7-41aa-a633-6a3493b97e4a` | ingest-watermark-skew-audit | `old/ingest-watermark-skew-audit` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `f6e9d77a-a5fb-478f-b52c-98994b9b50a4` | oidc-key-lifecycle-audit | `old/oidc-key-lifecycle-audit` | tracker-p1 + csv — **Wave 2 FAIL** (no Revise on 0479 queue) |
| `5f2d92cc-7a8f-401c-a397-a4a8f47cf026` | tsv-gap-bundle-audit | `old/tsv-gap-bundle-audit` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `fb9cc5df-5d5d-4fe2-bf89-175a4666085c` | attest-bundle-lattice | `old/attest-bundle-lattice` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `6040892f-37a1-47b8-8d7a-3ee68455888c` | breaker-ledger-audit | `old/breaker-ledger-audit` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `23f88a9b-27b3-4f3d-8134-f31f1f2e2fe6` | modreplace-lattice-audit | `old/modreplace-lattice-audit` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `2cb6ab3c-8725-4c19-b2da-7d3054c02627` | tls-cert-chain-auditor | `tls-cert-chain-auditor` | tracker-p1 + csv — **resubmitted 2026-05-23** |
| `c6ae9d08-406c-4607-b6dc-0ebc4d6ea170` | go-incident-cascade-auditor | `old/go-incident-cascade-auditor` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `6bdc8901-5d5e-4a3a-ac5f-55aaaee0b21f` | stream-shard-rebalancer | `old/stream-shard-rebalancer` | tracker-p1 + csv — **resubmitted Wave 2 2026-05-23** |
| `02b7c62d-f1f4-4b8e-903e-a0c065b0a57b` | csp-merge-policy-audit | `old/csp-merge-policy-audit` | csv — **resubmitted Wave 2 2026-05-23** |
| `093b3435-06d7-47d7-b3d0-445f89b8a06a` | *(no name in csv)* | — | csv — **blocked: resolve slug manually** |
| `14f3a711-4561-431b-a2c7-cd9bcb488392` | ml-experiment-ledger-auditor | `old/ml-experiment-ledger-auditor` | csv — **resubmitted Wave 2 2026-05-23** |
| `82b85d32-18cf-4184-b0cd-f0bbae6e465a` | go-module-bump-arbiter | `old/go-module-bump-arbiter` | csv — **Wave 2 FAIL** (no Revise on 0479 queue) |
| `91c375bf-3ab3-4fae-b647-c57bd0ce1d79` | sim-checkpoint-rollback-planner | `sim-checkpoint-plan-audit` | csv — **resubmitted Wave 2 2026-05-23** |

**Notes**

- Tracker page 1 alone matched **27** of 66; CSV + tracker union → **33**.
- `14f3a711` / `91c375bf`: platform says `NEEDS_REVISION`; tracker page 1 shows **Evaluation pending** for Girish — treat platform status as source of truth for resubmit.
- Paste **tracker page 2** when available to confirm `943ca427`, `02b7c62d`, etc.

---

## 3. Not Girish — 33 of 66

Platform `NEEDS_REVISION` with **no** Girish row in tracker page 1 or May CSV. Trainer from CSV where known.

| Task ID | Trainer (CSV) | Task name (CSV) |
|---------|---------------|-----------------|
| `115dcd7b-c285-4a4b-8acd-933cddef03d5` | Ganga | incident-chain-forensics-submission |
| `7377e1b7-2c3e-4704-a100-30bc8692accc` | Ganga | bash-hook-chain-audit |
| `17431386-697c-4e05-b6f4-2b2dace3d4c8` | Inshita | unit-pipeline-normalizer |
| `1c589fb1-3aa2-4a2f-b37c-4d2a6a51c617` | Inshita | ingest-lineage-auditor |
| `3b3e4434-79b4-4df6-8f7e-db0f7168fd15` | Inshita | thread-dump-reconcile-auditor |
| `4bd504b7-01e9-42c3-ab9c-604ea0bc9c2e` | Inshita | network-segment-policy-auditor |
| `4c5e54f3-7896-4f5d-a883-a9963e36e106` | Inshita | cmake-target-pin-auditor |
| `7eac7bd9-77dd-4c5d-8cd4-f9dcc9bdb407` | Inshita | replica-lag-window-audit |
| `81e753b5-5d97-4310-9fd5-0db8c378a5c4` | Inshita | grid-reachability-auditor |
| `9ec21e66-f325-4b0f-9ebb-efebd52be30f` | Inshita | backup-retention-auditor |
| `a73c7be3-959d-427c-85e3-1725533b42c0` | Megha | java-reentrant-fair-replay-hard |
| `81d28e74-6395-4fe2-b71e-e6ebdfe5c18c` | Shreya | ruby-interval-coalesce |
| `3c2c33b8-4177-4cd8-8a87-fa458807f7df` | — | — |
| `43736316-30a7-4c31-a7da-3d575427ed56` | — | — |
| `4c005e09-7d5b-4e9d-acfc-524fa794d003` | — | — |
| `65a57882-098e-4157-b242-ae5ce58e818a` | — | — |
| `69ac0fbc-54c6-4119-8688-20c1f860706f` | — | — |
| `6c649f96-8810-46df-91f7-5301bbdbdd38` | — | — |
| `720485cf-1e8f-4f6d-b5a7-a146b9d1b964` | — | — |
| `7df94103-d243-496b-a314-57e4ec662aef` | — | — |
| `8c8a70e9-c130-48d2-a8ab-c663ce90b874` | — | — |
| `8fd18659-22ec-4857-aac0-3248ba96b576` | — | — |
| `9ce46c81-d2e4-407a-9b47-a5c035a3f6a3` | — | — |
| `a38be328-5193-4de9-8fb9-3b7adc31f5bc` | — | — |
| `b03e0244-6eee-46fd-862a-f3e47d44ba1b` | — | — |
| `b3cca422-4c7a-4e55-a50f-8df1cb46074e` | — | — |
| `b65583f8-593b-4915-98a3-227f91d3c047` | — | — |
| `ce25bed2-7fde-4efb-816b-bbb32ac460c1` | — | — |
| `d3cde815-ad94-4ae7-9b17-120d8c8b9f57` | — | — |
| `d817ff4e-0ec9-4241-bcd2-b7e2ec010764` | — | — |
| `e7dcbc0a-558d-42c4-acf5-8f8820dae9af` | — | — |
| `f2562d6d-b25b-401c-9357-aec84edfb814` | — | — |
| `fea4937d-c7c0-4e6f-862b-604753327459` | — | — |

---

## 4. Girish `Needs Revision` in tracker — not in platform 66

May still need Snorkel resubmit or platform status lag:

| Task ID | Task name |
|---------|-----------|
| `7870689e-5c8a-4452-bac4-a76c025b44f8` | zone-ingress-matrix-audit | `zone-ingress-matrix-audit` | **Wave 2 FAIL** — not in platform 66 for 0479; submit manually |
| `7f690c0e-fa7d-467e-a15a-b51b93a8bbef` | ab-arm-allocation-audit | — | (see earlier session) |
| `470f83f7-2cab-47c4-97b8-2897a83a8aed` | lease-slot-coordinator-audit | — | (see earlier session) |
| `c752d785-a6a0-41c4-a1db-1955c756016b` | rod-pack-void-audit | `old/rod-pack-void-audit` | **Wave 2 FAIL** — not in platform 66 for 0479; submit manually |

---

## 5. Resubmit checklist (per task)

**Batch (Girish queue):**

1. `python tools/revision_wave_prep.py` — Wave 1 mechanical prep; see `e2e/audit/wave1-prep-latest.json`
2. Fix any `NEEDS_AGENT` rows (Dockerfile harness, offline `test.sh`, reviewer feedback in `e2e/audit/revision-<uuid>-context.json`)
3. `powershell -File e2e/scripts/wave2-submit.ps1 -OnlyReady` — Wave 2 serial E2E submits (updates `tasks/girish-revision-manifest.json`)

**Single task:**

1. `python tools/terminus-task-tools/terminus_zip.py preflight tasks/<slug>`
2. E2E: `SNORKEL_REVISION_TASK_ID=<uuid>` + `SNORKEL_UPLOAD_TASK_DIR=tasks/<slug>` → `npm run flow:revision:submit:headed`
3. Cycle 2: `regenerate_rubric` OFF, `Send to reviewer` ON (E2E defaults)

---

## 6. Related tooling

| Path | Purpose |
|------|---------|
| `snorkel-status-helper/snorkel-status-admin.user.js` | Dashboard badges; Girish filter via Google Sheet sync |
| `tools/_girish_revision_match.py` | Platform 66 ∩ CSV Girish |
| `tools/_girish_union.py` | Platform 66 ∩ (tracker p1 ∪ CSV) Girish |
| `tools/_tracker_page1.json` | Snapshot of Cognyzer API page 1 |
| `tools/revision_wave_prep.py` | Wave 1 batch prep (LF, leakage, preflight) |
| `e2e/scripts/wave2-submit.ps1` | Wave 2 serial revision submits from manifest |
| `tasks/girish-revision-manifest.json` | UUID → slug → uploadDir → status tracker |
| `e2e/.env.example` | `SNORKEL_TRAINER_NAME=Girish` for metadata rows |
| `tb2-build-completion-timeout.mdc` | 7200s difficulty-check timeout; slim Docker bases |
| [`JAVA_PORT_SUBMISSION_READY.md`](JAVA_PORT_SUBMISSION_READY.md) | Java-port batch: 19 zips + rubrics (2026-05-23) |
| `tools/verify_java_batch_submission.py` | Re-run preflight on all 19 Java-port zips |
| `tools/docker_verify_java_batch.py` | Docker build + oracle + pytest on all 19 |

---

## 7. Java port batch — submission ready (2026-05-23)

**19** accepted-task Java ports: local `terminus_zip.py preflight` ✅, flat zips at `tasks/<slug>.zip`, Docker oracle **19/19** green (1,095 pytest total).

**Rubric template:** [`antireplay-window-audit/rubrics.txt`](antireplay-window-audit/rubrics.txt) — each line `Agent …, +/-N` (N ∈ {1,2,3,5}), ≥3 negatives, positive sum 10–40. **Do not include `rubrics.txt` in the zip**; paste on platform cycle 1.

### Rubric reference (antireplay)

```
Agent writes every required JSON deliverable under `/app/output/` using canonical UTF-8 JSON from the task spec, +5
Agent implements the anti-replay window replay logic in TypeScript on Node 22 sources (.ts) under `/app/src/`, +3
Agent reads bundled inputs from `/app/data/` without altering fixture files, +2
…
Agent hardcodes expected outputs instead of computing them from the bundled inputs, -5
```

Java-port tasks use the same shape in each `tasks/<slug>/rubrics.txt` (Java instead of TypeScript where applicable).

### Upload table

| # | Local folder | Docker tests | Zip size | Zip | Rubrics (cycle 1 paste) |
|---|--------------|-------------:|---------:|-----|-------------------------|
| 1 | `systemd-unit-dep-audit` | 44 | 25,757 | [systemd-unit-dep-audit.zip](systemd-unit-dep-audit.zip) | [rubrics.txt](systemd-unit-dep-audit/rubrics.txt) |
| 2 | `git-hook-gate-audit` | 97 | 29,740 | [git-hook-gate-audit.zip](git-hook-gate-audit.zip) | [rubrics.txt](git-hook-gate-audit/rubrics.txt) |
| 3 | `schema-drift-impact-audit` | 56 | 45,901 | [schema-drift-impact-audit.zip](schema-drift-impact-audit.zip) | [rubrics.txt](schema-drift-impact-audit/rubrics.txt) |
| 4 | `k8s-rollout-impact-audit` | 45 | 42,591 | [k8s-rollout-impact-audit.zip](k8s-rollout-impact-audit.zip) | [rubrics.txt](k8s-rollout-impact-audit/rubrics.txt) |
| 5 | `npm-mono-bump-audit` | 99 | 31,094 | [npm-mono-bump-audit.zip](npm-mono-bump-audit.zip) | [rubrics.txt](npm-mono-bump-audit/rubrics.txt) |
| 6 | `cargo-ws-bump-audit` | 109 | 34,748 | [cargo-ws-bump-audit.zip](cargo-ws-bump-audit.zip) | [rubrics.txt](cargo-ws-bump-audit/rubrics.txt) |
| 7 | `pay-ledger-recon-audit` | 22 | 42,581 | [pay-ledger-recon-audit.zip](pay-ledger-recon-audit.zip) | [rubrics.txt](pay-ledger-recon-audit/rubrics.txt) |
| 8 | `crash-sig-triage-audit` | 96 | 31,899 | [crash-sig-triage-audit.zip](crash-sig-triage-audit.zip) | [rubrics.txt](crash-sig-triage-audit/rubrics.txt) |
| 9 | `hitl-queue-consensus-audit` | 53 | 21,223 | [hitl-queue-consensus-audit.zip](hitl-queue-consensus-audit.zip) | [rubrics.txt](hitl-queue-consensus-audit/rubrics.txt) |
| 10 | `ssh-compliance-audit` | 35 | 51,595 | [ssh-compliance-audit.zip](ssh-compliance-audit.zip) | [rubrics.txt](ssh-compliance-audit/rubrics.txt) |
| 11 | `cryostat-lattice-audit` | 69 | 28,083 | [cryostat-lattice-audit.zip](cryostat-lattice-audit.zip) | [rubrics.txt](cryostat-lattice-audit/rubrics.txt) |
| 12 | `stokes-diffusion-audit` | 27 | 1,988,813 | [stokes-diffusion-audit.zip](stokes-diffusion-audit.zip) | [rubrics.txt](stokes-diffusion-audit/rubrics.txt) |
| 13 | `ledger-event-recon-audit` | 30 | 35,745 | [ledger-event-recon-audit.zip](ledger-event-recon-audit.zip) | [rubrics.txt](ledger-event-recon-audit/rubrics.txt) |
| 14 | `keytab-rotation-audit` | 112 | 38,305 | [keytab-rotation-audit.zip](keytab-rotation-audit.zip) | [rubrics.txt](keytab-rotation-audit/rubrics.txt) |
| 15 | `proc-tree-reaper-audit` | 48 | 49,000 | [proc-tree-reaper-audit.zip](proc-tree-reaper-audit.zip) | [rubrics.txt](proc-tree-reaper-audit/rubrics.txt) |
| 16 | `detector-telem-cal-audit` | 35 | 38,022 | [detector-telem-cal-audit.zip](detector-telem-cal-audit.zip) | [rubrics.txt](detector-telem-cal-audit/rubrics.txt) |
| 17 | `seismic-loc-qc-audit` | 23 | 43,910 | [seismic-loc-qc-audit.zip](seismic-loc-qc-audit.zip) | [rubrics.txt](seismic-loc-qc-audit/rubrics.txt) |
| 18 | `spectral-cal-audit` | 27 | 35,339 | [spectral-cal-audit.zip](spectral-cal-audit.zip) | [rubrics.txt](spectral-cal-audit/rubrics.txt) |
| 19 | `sim-checkpoint-plan-audit` | 100 | 47,629 | [sim-checkpoint-plan-audit.zip](sim-checkpoint-plan-audit.zip) | [rubrics.txt](sim-checkpoint-plan-audit/rubrics.txt) |

**Girish queue overlap:** §2 lists `stokes-diffusion-audit` (`49f2e499…`) and `sim-checkpoint-rollback-planner` → local `sim-checkpoint-plan-audit` (`91c375bf…`) as `NEEDS_REVISION`; rows 12 and 19 above are resubmit candidates.

**Excluded:** `go-race-deadlock-audit` (Go debug task, not Gson audit).

**Re-verify before upload:**

```powershell
python tools/verify_java_batch_submission.py
python tools/docker_verify_java_batch.py
python tools/terminus-task-tools/terminus_zip.py preflight tasks/<slug>
```

**Source mapping:** [`tools/accepted_java_conversion_plan.md`](../tools/accepted_java_conversion_plan.md), scaffold queue [`_JAVA_SCAFFOLD_QUEUE.md`](_JAVA_SCAFFOLD_QUEUE.md).

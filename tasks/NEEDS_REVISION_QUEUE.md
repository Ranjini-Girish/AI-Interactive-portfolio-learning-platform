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
| `ea5f4223-d084-436e-9a54-8acb7fa45f3f` | ansible-dependency-impact-task | `ansible-dependency-impact-task` | tracker-p1 |
| `b0907c07-03af-45c7-8136-028704d18838` | wal-index-trim-audit | `wal-index-trim-audit` | tracker-p1 |
| `e0705c3d-623e-4701-823f-4fd683c8a48a` | rle-bursts-merge-audit | — | tracker-p1 |
| `8d198124-d872-4df6-9ef7-3d03eac93ddd` | ledger-epoch-skew-audit | — | tracker-p1 |
| `faf82617-f62d-4b79-acfb-4f4e0aa3bce0` | pawn-endgame-table-audit | `pawn-endgame-table-audit` | tracker-p1 |
| `d13b444b-40f6-46d9-8632-b89bf88ae7ee` | trap-grid-chain-audit | `trap-grid-chain-audit` | tracker-p1 + csv |
| `6d4acddc-3202-4b70-9e61-0b6c32e0bfd8` | slo-burn-window-audit | `slo-burn-window-audit` | tracker-p1 + csv |
| `2fd03871-d392-44a6-b133-00c9bb542cd5` | cdc-lag-compactor-audit | — | tracker-p1 + csv |
| `5b3b84d0-fea4-48ae-ae03-3e670f3cabec` | sensor-calib-lattice-audit | — | tracker-p1 + csv |
| `49f2e499-d969-4241-986b-074919b78452` | stokes-diffusion-audit | — | tracker-p1 + csv |
| `f4bf1aec-a79d-4681-a053-971e215eea2d` | webhook-retry-ledger-audit | — | tracker-p1 + csv |
| `a711d7b8-a9a9-4e40-88e9-95d3272ac3e1` | replica-lag-window-audit | `replica-lag-window-audit` | tracker-p1 + csv |
| `943ca427-4fb0-4f13-8a48-6379ac6097ff` | replica-lag-window-audit | `replica-lag-window-audit` | csv |
| `880ff0fc-751e-4495-aeb8-77827cee6ce5` | train-slot-lattice-audit | — | tracker-p1 + csv |
| `de430a3a-c0e4-45a5-a9e8-f072d9816e52` | infer-blend-quota-audit | — | tracker-p1 + csv |
| `2fdf3090-0206-4a34-9dc2-dce225fd2593` | initiative-clash-audit | — | tracker-p1 + csv |
| `335be3bf-cc8d-4016-8894-5a4b00fc4054` | patch-slot-lattice-audit | — | tracker-p1 + csv |
| `3665a277-0a6b-4ba3-910b-31b8e25af67b` | export-batch-window-audit | — | tracker-p1 + csv |
| `c0c86689-5c55-47c8-a238-7ad18532a5c9` | artifact-promote-lattice-audit | — | tracker-p1 + csv |
| `1cec7fb5-cbe7-41aa-a633-6a3493b97e4a` | ingest-watermark-skew-audit | — | tracker-p1 + csv |
| `f6e9d77a-a5fb-478f-b52c-98994b9b50a4` | oidc-key-lifecycle-audit | — | tracker-p1 + csv |
| `5f2d92cc-7a8f-401c-a397-a4a8f47cf026` | tsv-gap-bundle-audit | — | tracker-p1 + csv |
| `fb9cc5df-5d5d-4fe2-bf89-175a4666085c` | attest-bundle-lattice | — | tracker-p1 + csv |
| `6040892f-37a1-47b8-8d7a-3ee68455888c` | breaker-ledger-audit | — | tracker-p1 + csv |
| `23f88a9b-27b3-4f3d-8134-f31f1f2e2fe6` | modreplace-lattice-audit | — | tracker-p1 + csv |
| `2cb6ab3c-8725-4c19-b2da-7d3054c02627` | tls-cert-chain-auditor | `tls-cert-chain-auditor` | tracker-p1 + csv |
| `c6ae9d08-406c-4607-b6dc-0ebc4d6ea170` | go-incident-cascade-auditor | — | tracker-p1 + csv |
| `6bdc8901-5d5e-4a3a-ac5f-55aaaee0b21f` | stream-shard-rebalancer | — | tracker-p1 + csv |
| `02b7c62d-f1f4-4b8e-903e-a0c065b0a57b` | csp-merge-policy-audit | — | csv |
| `093b3435-06d7-47d7-b3d0-445f89b8a06a` | *(no name in csv)* | — | csv |
| `14f3a711-4561-431b-a2c7-cd9bcb488392` | ml-experiment-ledger-auditor | — | csv |
| `82b85d32-18cf-4184-b0cd-f0bbae6e465a` | go-module-bump-arbiter | — | csv |
| `91c375bf-3ab3-4fae-b647-c57bd0ce1d79` | sim-checkpoint-rollback-planner | `sim-checkpoint-plan-audit` | csv |

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
| `7870689e-5c8a-4452-bac4-a76c025b44f8` | zone-ingress-matrix-audit |
| `7f690c0e-fa7d-467e-a15a-b51b93a8bbef` | ab-arm-allocation-audit |
| `470f83f7-2cab-47c4-97b8-2897a83a8aed` | lease-slot-coordinator-audit |
| `c752d785-a6a0-41c4-a1db-1955c756016b` | rod-pack-void-audit |

---

## 5. Resubmit checklist (per task)

1. `python tools/terminus-task-tools/terminus_zip.py preflight tasks/<slug>`
2. `build` → upload flat zip (not `rubrics.txt`)
3. Cycle 1: `regenerate_rubric` ON, `Send to Reviewer` OFF — paste `rubrics.txt`
4. Cycle 2: `regenerate_rubric` OFF, `Send to Reviewer` ON

---

## 6. Related tooling

| Path | Purpose |
|------|---------|
| `snorkel-status-helper/snorkel-status-admin.user.js` | Dashboard badges; Girish filter via Google Sheet sync |
| `tools/_girish_revision_match.py` | Platform 66 ∩ CSV Girish |
| `tools/_girish_union.py` | Platform 66 ∩ (tracker p1 ∪ CSV) Girish |
| `tools/_tracker_page1.json` | Snapshot of Cognyzer API page 1 |
| `e2e/.env.example` | `SNORKEL_TRAINER_NAME=Girish` for metadata rows |

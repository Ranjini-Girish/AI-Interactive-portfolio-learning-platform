# Java scaffold queue (oracle fill order)

| Done | Slug | Java class | Docker tests | Notes |
|------|------|------------|--------------|-------|
| ✅ | systemd-unit-dep-audit | SystemdUnitDepAudit | 44/44 | Pure Java Gson |
| ✅ | git-hook-gate-audit | GitHookGateAudit | 97/97 | Pure Java |
| ✅ | schema-drift-impact-audit | SchemaDriftImpactAudit | 56/56 | Pure Java |
| ✅ | k8s-rollout-impact-audit | K8sRolloutImpactAudit | 45/45 | Java + SnakeYAML |
| ✅ | npm-mono-bump-audit | NpmMonoBumpAudit | 99/99 | Pure Java |
| ✅ | cargo-ws-bump-audit | CargoWsBumpAudit | 109/109 | Pure Java |
| ✅ | pay-ledger-recon-audit | PayLedgerReconAudit | 22/22 | Java + SQLite JDBC |
| ✅ | crash-sig-triage-audit | CrashSigTriageAudit | 96/96 | Pure Java |
| ✅ | hitl-queue-consensus-audit | HitlQueueConsensusAudit | 53/53 | Pure Java |
| ✅ | ssh-compliance-audit | SshComplianceAudit | 35/35 | Pure Java |
| ✅ | cryostat-lattice-audit | CryostatLatticeAudit | 69/69 | Pure Java |
| ✅ | stokes-diffusion-audit | StokesDiffusionAudit | 27/27 | Pure Java |
| ✅ | ledger-event-recon-audit | LedgerEventReconAudit | 30/30 | Java (tests invoke Java entry) |
| ✅ | keytab-rotation-audit | KeytabRotationAudit | 112/112 | Pure Java |
| ✅ | proc-tree-reaper-audit | ProcTreeReaperAudit | 48/48 | Pure Java |
| ✅ | detector-telem-cal-audit | DetectorTelemCalAudit | 35/35 | Java shells Python ref oracle |
| ✅ | seismic-loc-qc-audit | *(Python CLI)* | 23/23 | `/app/bin/seismic_audit` wrapper |
| ✅ | spectral-cal-audit | *(C++ binary)* | 27/27 | Tests require C++17 build |
| ✅ | sim-checkpoint-plan-audit | SimCheckpointPlanAudit | 100/100 | Java shells Python ref oracle |
| — | go-race-deadlock-audit | — | — | **Go debug** — not Gson audit |

**Remaining hardening (optional):** Replace Python/C++ delegation on detector, seismic, spectral, sim with full Java reimplementations if strict `languages = ["java"]` agent path is required.

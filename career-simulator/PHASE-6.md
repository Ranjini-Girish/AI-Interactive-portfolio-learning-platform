# Phase 6 — Job simulation modules

## What this phase delivers

Four **interactive work simulations** with real company-style tasks:

| Role | Company scenario | Tasks |
|------|------------------|-------|
| **QA Tester** | ValleyPay mobile banking login | Test cases, bug report, defect triage, regression vs smoke |
| **Data Analyst** | Northwest Health Q1 sales | Dataset insights, chart narrative, SQL thinking, exec summary |
| **Project Manager** | Customer portal redesign | Project plan, risks, sprint backlog, status email |
| **AI Reviewer** | SafeReply model audit | Rubric, rate samples, feedback, reviewer checklist |

Each module has **4 sequential tasks**. Submit work → instant rubric-based feedback → pass to unlock the next task.

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/simulation/modules` | All modules + user progress |
| GET | `/api/simulation/modules/:roleId` | Module detail + task definitions |
| POST | `/api/simulation/sessions/:roleId/start` | Start or resume session |
| GET | `/api/simulation/sessions/:roleId` | Session + task statuses |
| GET | `/api/simulation/tasks/:roleId/:taskId/fixtures` | Task + datasets/defects/samples |
| POST | `/api/simulation/tasks/:roleId/:taskId/submit` | Grade submission |
| GET | `/api/simulation/stats` | Aggregate completion counts |

---

## Database

Migration `005_simulations.sql`:

- `simulation_sessions` — one row per user per role
- `simulation_submissions` — graded task payloads + scores

---

## How to test

1. Sign in, complete resume + job match (Phases 3–4) — optional but recommended
2. Go to **http://localhost:3000/roles**
3. Click **Start simulation** on **QA Tester**
4. Complete Task 1 (test cases) — use numbered steps + expected results
5. Submit — score ≥ 70% unlocks Task 2
6. Try **Data Analyst** module — dataset table appears on explore task
7. Dashboard shows tasks completed + in-progress module

---

## Key files

```
apps/api/src/data/simulations/     # Module + task definitions
apps/api/src/services/simulation-grader.ts
apps/api/src/routes/simulation.ts
apps/web/src/app/roles/              # List + module + task pages
packages/shared/src/simulation.ts    # Shared types
```

---

## Next phase

**Phase 7 — Dashboard + progress tracking** (enhanced analytics, weak areas, suggested next steps)

Reply **"continue Phase 7"** when ready.

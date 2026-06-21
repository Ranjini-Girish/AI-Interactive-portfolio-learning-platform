# Phase 7 — Dashboard + progress tracking

## What this phase delivers

A **full progress dashboard** at `/dashboard` that aggregates resume, job match, and simulation data:

| Section | What it shows |
|---------|----------------|
| **Job readiness** | Composite score (0–100) with label: Getting started → Job ready |
| **Score breakdown** | Resume match %, job match %, simulation progress % |
| **Stats grid** | Skills identified, skills practiced, tasks passed, modules done |
| **Project completion** | Average progress across all 4 simulation modules |
| **Suggested next steps** | Prioritized actions with deep links |
| **Weak areas** | Resume gaps, job skill gaps, missing tools, tasks needing revision |
| **Skills learned** | Combined skill chips from resume + job + practice |
| **Module progress** | Per-role simulation bars with Continue links |
| **Learning path** | Step tracker from job match or resume roadmap |

---

## Readiness formula

Weighted average (normalized to available data):

- **25%** — top resume role match score
- **35%** — latest job description match score
- **40%** — simulation tasks passed (out of 16 total)

Labels:

| Score | Label |
|-------|-------|
| 0–24 | Getting started |
| 25–54 | Building skills |
| 55–79 | Interview ready |
| 80+ | Job ready |

---

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/progress/dashboard` | Full `ProgressDashboard` payload |
| GET | `/api/auth/dashboard` | Legacy alias (includes `progress` nested object) |

Types live in `packages/shared/src/progress.ts`.

---

## How to test

1. Sign in with an account that has resume + job match + some simulation progress
2. Open **http://localhost:3000/dashboard**
3. Verify readiness score and breakdown update after passing a simulation task
4. Check **Weak areas** lists job skill gaps
5. **Suggested next steps** should point to the highest-priority action
6. Complete all 4 modules — readiness should climb toward "Job ready"

Fresh account flow:

1. Dashboard shows low readiness + "Upload resume" as step 1
2. After resume → job match → simulation, each section fills in

---

## Key files

```
apps/api/src/services/progress-dashboard.ts   # Aggregation logic
apps/api/src/routes/progress.ts
apps/web/src/components/dashboard/            # UI panels
apps/web/src/app/dashboard/page.tsx
packages/shared/src/progress.ts
```

---

## Next phase

**Phase 8 — Portfolio generator** (resume bullets, LinkedIn copy, project summaries)

Reply **"continue Phase 8"** when ready.

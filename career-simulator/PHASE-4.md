# Phase 4 — Job description matching engine

## What this phase delivers

Compare any **job description** against the user's **latest resume analysis**:

- Required vs preferred skills extracted from JD
- Tools mentioned (Jira, Selenium, Power BI, etc.)
- **Skill gaps** and **missing tools**
- **Overall match score** (0–99%)
- **Learning path** to close gaps before applying

---

## API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/job/samples` | No | 3 sample job postings |
| POST | `/api/job/match` | Yes | `{ jdText, targetRole?, resumeAnalysisId? }` |
| POST | `/api/job/match-sample` | Yes | `{ sampleId }` |
| GET | `/api/job/latest` | Yes | Latest match for user |

Requires a resume analysis on file (Phase 3).

---

## Sample job postings

| ID | Role |
|----|------|
| `qa-fintech` | QA Tester — mobile banking |
| `data-analyst-remote` | Data Analyst I |
| `pm-insurance` | Project Coordinator / Junior PM |

---

## How matching works

1. Extract skills & tools from JD text (shared taxonomy with resume parser)
2. Split **required** vs **nice to have** sections
3. Fuzzy-match JD requirements against resume skills
4. Score = required coverage (85%) + preferred bonus (15%)
5. Generate learning steps for gaps and missing tools

---

## How to test

```powershell
cd career-simulator
npm run db:up
npm run dev
```

1. Sign in  
2. **Resume** → analyze **QA career returner** sample  
3. **Job match** → **QA Tester — Mobile Banking** → **Match against my resume**  
4. Expect high match %, few gaps (Jira, Postman, manual testing overlap)  
5. Try **Data Analyst JD** against same resume → lower score, Python/SQL gaps  

Dashboard updates with match score and gap count.

---

## Key files

```
apps/api/src/services/skill-taxonomy.ts   # shared skill/tool patterns
apps/api/src/services/jd-matcher.ts
apps/api/src/routes/job.ts
apps/api/src/data/samples/jobs.ts
apps/web/src/app/job/page.tsx
```

---

## Next phase

**Phase 5 — AI Live Mentor** (streaming OpenAI chat sidebar)

Reply **"continue Phase 5"** when ready.

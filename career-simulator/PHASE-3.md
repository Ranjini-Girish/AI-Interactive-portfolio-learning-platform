# Phase 3 — Resume parser + analyzer

## What this phase delivers

Signed-in users can **upload PDF/DOCX/TXT**, **paste text**, or **try bundled sample resumes**. The engine extracts skills, experience, and projects, then generates:

- Job match scores (all 4 simulation roles)
- Learning roadmap (step-by-step)
- Practice project suggestions
- Strengths & skill gaps

Results are saved to PostgreSQL per user.

---

## API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/resume/samples` | No | List 3 sample resume personas |
| POST | `/api/resume/analyze-text` | Yes | `{ text, targetRole? }` |
| POST | `/api/resume/analyze-sample` | Yes | `{ sampleId, targetRole? }` |
| POST | `/api/resume/upload` | Yes | `multipart/form-data` field `file` |
| GET | `/api/resume/latest` | Yes | Most recent analysis |
| GET | `/api/resume/:id` | Yes | Specific analysis by UUID |

---

## Sample resumes

| ID | Persona |
|----|---------|
| `qa-returner` | QA pro, 3 yrs, career gap, restarting |
| `fresher-analyst` | Stats grad, internships, Python/Excel |
| `pm-coordinator` | Insurance project coordinator → PM |

---

## How parsing works

1. **File → text** — `pdf-parse` (PDF), `mammoth` (DOCX), UTF-8 (TXT)
2. **Skill extraction** — keyword patterns + SKILLS section parsing
3. **Experience** — date ranges and “X years” phrases
4. **Projects** — PROJECTS section bullet lines
5. **Scoring** — required/nice skills per role → 0–98% match
6. **Roadmap** — role-specific steps + gap-closing module

Optional `targetRole` overrides auto-detect for roadmap generation.

---

## How to test

```powershell
cd career-simulator
npm run db:up
npm run dev
```

1. Sign in at http://localhost:3000/login  
2. Go to **Resume** (or http://localhost:3000/resume)  
3. **Try sample** → “QA career returner” → **Analyze**  
4. Review job match scores, roadmap, practice projects  
5. Check **Dashboard** — readiness % and skills count update  

### curl (with token)

```powershell
# Analyze sample
curl -X POST http://localhost:4000/api/resume/analyze-sample `
  -H "Authorization: Bearer YOUR_JWT" `
  -H "Content-Type: application/json" `
  -d '{"sampleId":"qa-returner"}'
```

---

## Key files

```
apps/api/src/
  services/resume-parser.ts    # PDF/DOCX → text
  services/resume-analyzer.ts  # extraction + scoring
  routes/resume.ts
  data/samples/              # bundled resumes
  db/migrations/002_resumes.sql

apps/web/src/
  app/resume/page.tsx
  components/resume/analysis-results.tsx
```

---

## Next phase

**Phase 4 — Job description matching**

- Paste any JD  
- Skill gap vs resume  
- Missing tools & suggested learning path  

Reply **"continue Phase 4"** when ready.

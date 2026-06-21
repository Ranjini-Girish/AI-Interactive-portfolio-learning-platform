# Phase 9 — Mock interview system

## What this phase delivers

Practice interviews at **`/interview`** with:

- **Behavioral** questions (STAR method)
- **Technical** questions per role (QA, Data Analyst, PM, AI Reviewer)
- **Mixed** mode (3 + 3)
- Instant **scoring** (0–100 per answer)
- **Strengths**, **improvements**, and sample answer structure
- **Overall score** + improvement plan when session completes

OpenAI feedback when `OPENAI_API_KEY` is set; local rubric coach otherwise.

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/interview/status` | AI configured? resume present? |
| GET | `/api/interview/sessions` | Recent sessions (last 20) |
| POST | `/api/interview/sessions` | Start `{ roleId, interviewType }` |
| GET | `/api/interview/sessions/:id` | Session + responses + pending questions |
| POST | `/api/interview/sessions/:id/answer` | Submit `{ questionId, answer }` |

---

## Database

Migration `007_interviews.sql`:

- `interview_sessions` — role, type, scores, question IDs
- `interview_responses` — answers + feedback JSON per question

---

## How to test

1. Sign in → **http://localhost:3000/interview**
2. Pick **QA Tester** + **Mixed**
3. Click **Start mock interview**
4. Answer with 60+ words using STAR (Situation, Task, Action, Result)
5. Submit — review feedback score and tips
6. Click **Next question** until complete
7. View **overall score** and improvement plan

Try a short answer (&lt; 30 words) — validation should block submit.

---

## Key files

```
apps/api/src/data/interviews/questions.ts
apps/api/src/services/interview-grader.ts
apps/api/src/routes/interview.ts
apps/web/src/app/interview/
packages/shared/src/interview.ts
```

---

## Next phase

**Phase 10 — Deployment** (Vercel web + Render/Railway API + managed Postgres)

Reply **"continue Phase 10"** when ready.

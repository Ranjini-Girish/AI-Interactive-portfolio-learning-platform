# Phase 8 — Portfolio generator

## What this phase delivers

Auto-generated career artifacts at **`/portfolio`**, built from:

- Resume analysis (skills, projects, headline)
- Job match (target role, gaps)
- Completed simulation work (QA, Data Analyst, PM, AI Reviewer)

### Output sections

| Tab | Content |
|-----|---------|
| **Resume bullets** | 5–8 action-oriented bullets with copy button |
| **LinkedIn** | Headline + About section |
| **Projects** | Per-simulation summaries with bullets and skills |
| **GitHub README** | Markdown portfolio README |

**OpenAI** polishes copy when `OPENAI_API_KEY` is set; **local templates** work offline.

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio/status` | Resume present? prior generation? AI configured? |
| GET | `/api/portfolio/latest` | Most recent saved portfolio |
| POST | `/api/portfolio/generate` | Generate + save new portfolio |

---

## Database

Migration `006_portfolios.sql` — `portfolio_generations` table stores JSON content per generation (history preserved).

---

## How to test

1. Sign in with resume analyzed (and ideally some simulation tasks completed)
2. Open **http://localhost:3000/portfolio**
3. Click **Generate portfolio**
4. Switch tabs — copy resume bullets and LinkedIn text
5. Complete more simulation tasks → **Regenerate** — projects section should grow
6. With `OPENAI_API_KEY` set, badge shows "AI-enhanced"

Without resume: page prompts you to `/resume` first.

---

## Key files

```
apps/api/src/services/portfolio-generator.ts
apps/api/src/routes/portfolio.ts
apps/web/src/app/portfolio/page.tsx
apps/web/src/components/portfolio/portfolio-view.tsx
packages/shared/src/portfolio.ts
```

---

## Next phase

**Phase 9 — Mock interview system** (behavioral + technical questions, AI feedback, scoring)

Reply **"continue Phase 9"** when ready.

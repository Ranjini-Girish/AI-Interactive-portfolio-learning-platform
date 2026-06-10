# Quick start — everything running

## One-click start (after first setup)

Double-click:

```
portfolio-mentor-platform/START-PORTFOLIO.bat
```

Or in PowerShell:

```powershell
cd "c:\Users\ranji\Airdawg_terminal latest code\portfolio-mentor-platform"
powershell -ExecutionPolicy Bypass -File scripts\start-all.ps1
```

## Open in browser

| What | URL |
|------|-----|
| **Main website** | http://localhost:3200 |
| Build Lab | http://localhost:3200/build |
| Portfolio demos | http://localhost:3200/portfolio |
| Contact form | http://localhost:3200/contact |
| P01 Segmentation | http://localhost:5173 |
| P02 Churn API | http://localhost:5174 |
| P03 Reco Shop | http://localhost:5175 |

## First-time setup (already done on your machine)

- Node.js 24 LTS
- Python 3.12
- `npm install` in website + 3 frontends
- Python venvs + pip deps for 3 backends
- P02 model trained, P03 database seeded

## Stop servers

Close the minimized PowerShell windows opened by `start-all.ps1`, or end Node/Python processes in Task Manager.

## Deploy website to Vercel

See [DEPLOY.md](./DEPLOY.md). Demo apps (P01–P03) stay local unless you deploy them separately to Railway/Render.

## Audio AI tutor (Build Lab project pages)

Open any project under **Build Lab** — the **Audio AI Tutor** panel reads each step aloud:

1. Click **Start walkthrough** (or it auto-starts when you open a new step)
2. Hear: intro → instructions → hint → each checklist item → wrap-up
3. Toggle **Voice commands** and say: *"next"*, *"repeat"*, *"stop"*, *"mentor feedback"*
4. **OpenAI premium voice**: set `OPENAI_API_KEY` in `.env.local` and choose "OpenAI premium" in the voice dropdown

Uses browser speech by default (no API key needed).

## Optional env

Copy `.env.example` → `.env.local` for OpenAI mentor + Resend contact email.

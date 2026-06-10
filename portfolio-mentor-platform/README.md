# Ranjini Gowda — AI Portfolio & Build Lab

Unified website: **public portfolio** + **hands-on build lab** + **live demo launcher** for resume-backed projects.

## Run the site

```powershell
cd portfolio-mentor-platform
npm install
npm run dev
```

Open **http://localhost:3200**

## Site map

| Page | URL | Purpose |
|------|-----|---------|
| Home | `/` | Hero, skills, stats, CTAs |
| Portfolio | `/portfolio` | All 12 apps — launch demos or open Build Lab |
| Build Lab | `/build` | Milestones, progress, mentor workspace |
| Experience | `/experience` | Resume work history |
| Mentoring plan | `/plan` | 14-week phased roadmap |
| Demo launcher | `/demos/[slug]` | Run P01–P03 locally (embed or new tab) |
| Contact | `/contact` | Contact form (Resend or mailto) |
| Project workspace | `/build/projects/[slug]` | Steps, checklist, AI mentor |

## Deploy to Vercel

See **[DEPLOY.md](./DEPLOY.md)** — import with root `portfolio-mentor-platform`, set `RESEND_API_KEY` for email delivery.

## Contact form

`/contact` uses Resend when configured; otherwise returns a mailto fallback.

## Run portfolio apps (alongside the site)

| App | Backend | Frontend |
|-----|---------|----------|
| P01 Segmentation | `:8000` | `:5173` |
| P02 Churn API | `:8001` | `:5174` |
| P03 Recommendations | `:8002` | `:5175` |
| **This website** | — | `:3200` |

From `/portfolio` → **Launch demo** on scaffolded projects.

## Optional: live AI mentor

`.env.local`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

## Repo layout

```
portfolio-mentor-platform/   ← this website
apps/
  p01-customer-segmentation/
  p02-churn-api/
  p03-recommendations/
```

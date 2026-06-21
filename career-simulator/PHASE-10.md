# Phase 10 — Deployment (Vercel + Render)

> **Quick start:** see [`DEPLOY-RUNBOOK.md`](./DEPLOY-RUNBOOK.md) for copy/paste GitHub → Render → Vercel steps.

## Architecture

```
┌─────────────────┐     HTTPS      ┌──────────────────┐
│  Vercel         │ ──────────────▶│  Render (Docker) │
│  apps/web       │   REST + SSE   │  Dockerfile.api  │
│  Next.js 15     │                │  Express API     │
└─────────────────┘                └────────┬─────────┘
                                            │
                                            ▼
                                   ┌──────────────────┐
                                   │ Render Postgres  │
                                   │ (managed)        │
                                   └──────────────────┘
```

---

## Files added

| File | Purpose |
|------|---------|
| `Dockerfile.api` | Production API container |
| `render.yaml` | Render Blueprint (API + Postgres) |
| `apps/web/vercel.json` | Monorepo build commands for Vercel |
| `.env.production.example` | Production env reference |
| `.dockerignore` | Slim Docker build context |

---

## 1. Deploy API on Render

### Option A — Blueprint (recommended)

1. Push `career-simulator/` to GitHub
2. [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**
3. Connect repo, select `render.yaml`
4. After deploy, open **career-sim-api** → **Environment**:
   - `CORS_ORIGIN` = your Vercel URL (e.g. `https://career-sim.vercel.app`)
   - `OPENAI_API_KEY` = your key (optional — local fallbacks work)
   - `PUBLIC_API_URL` = `https://career-sim-api.onrender.com` (your service URL)
5. Copy the public API URL for Vercel

### Option B — Manual Docker service

```bash
cd career-simulator
docker build -f Dockerfile.api -t career-sim-api .
docker run -p 4000:4000 \
  -e DATABASE_URL=postgresql://... \
  -e JWT_SECRET=... \
  -e CORS_ORIGIN=https://your-app.vercel.app \
  career-sim-api
```

Migrations run automatically on API startup (`runMigrations()`).

---

## 2. Deploy Web on Vercel

1. [Vercel Dashboard](https://vercel.com) → **Add New Project** → import GitHub repo
2. **Root Directory:** `career-simulator/apps/web`
3. Framework: **Next.js** (auto-detected)
4. `apps/web/vercel.json` sets install/build from monorepo root
5. **Environment variables:**

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://career-sim-api.onrender.com` |
| `NEXT_PUBLIC_APP_NAME` | `AI Career Transition Simulator` |

6. Deploy → open your `*.vercel.app` URL

---

## 3. Wire CORS (critical)

On Render, set:

```
CORS_ORIGIN=https://your-production.vercel.app,https://your-preview.vercel.app
```

Comma-separated — no trailing slashes. Without this, browser login/API calls fail.

---

## 4. Verify production

```bash
curl https://career-sim-api.onrender.com/api/health
```

Expect `"phase": 10`, `"database": "connected"`, `"deploy": "production_ready"`.

Then on Vercel site:

1. Register / login
2. Resume → job match → simulation → portfolio → interview
3. Mentor sidebar streams (needs `OPENAI_API_KEY` on Render)

---

## Local production smoke test

```powershell
cd career-simulator
npm run build
npm run docker:api
# In another terminal with .env pointing to local Postgres:
docker run --rm -p 4000:4000 --env-file .env career-sim-api
```

---

## Environment checklist

| Variable | Where | Required |
|----------|-------|----------|
| `DATABASE_URL` | Render | Yes |
| `JWT_SECRET` | Render | Yes (auto-generated in Blueprint) |
| `CORS_ORIGIN` | Render | Yes |
| `OPENAI_API_KEY` | Render | Optional |
| `NEXT_PUBLIC_API_URL` | Vercel | Yes |
| `PUBLIC_API_URL` | Render | Optional (logging) |

See `.env.production.example` for full list.

---

## Platform complete

All 10 phases of the Career Transition Simulator are implemented:

1. Monorepo setup  
2. JWT auth  
3. Resume analyzer  
4. Job matching  
5. AI mentor (SSE)  
6. Job simulations  
7. Progress dashboard  
8. Portfolio generator  
9. Mock interviews  
10. **Production deployment**

You now have a deployable full-stack learning platform.

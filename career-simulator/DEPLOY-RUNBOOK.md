# Deploy runbook — copy/paste checklist

Use this after `scripts/pre-deploy.ps1` passes locally.

---

## Choose your Git layout

| Option | Best for | Render | Vercel root |
|--------|----------|--------|-------------|
| **A — Dedicated repo** (recommended) | Cleanest deploy | `render.yaml` at repo root | `apps/web` |
| **B — Parent monorepo** | Keep inside `Airdawg_terminal` | Use `render.monorepo.yaml` at **parent** repo root | `career-simulator/apps/web` |

---

## Step 1 — GitHub push

### Option A — New repo with only `career-simulator/`

```powershell
cd "c:\Users\ranji\Airdawg_terminal latest code\career-simulator"
git init
git add .
git commit -m "Initial commit: AI Career Transition Simulator (phases 1-10)"
git branch -M main
# Create empty repo on GitHub, then:
git remote add origin https://github.com/YOUR_USER/career-simulator.git
git push -u origin main
```

### Option B — Add to existing repo

```powershell
cd "c:\Users\ranji\Airdawg_terminal latest code"
git add career-simulator/
git commit -m "Add career-simulator platform (phases 1-10)"
git push origin main
```

Copy `render.monorepo.yaml` from the parent repo root to `render.yaml` before using Render Blueprint (see Option B below).

---

## Step 2 — Render (API + Postgres)

1. Open https://dashboard.render.com → **New** → **Blueprint**
2. Connect your GitHub repo
3. **Option A:** Blueprint finds `render.yaml` in repo root  
   **Option B:** At parent repo root, rename/copy `render.monorepo.yaml` → `render.yaml` (or point Blueprint at it)
4. Click **Apply** — creates `career-sim-api` + `career-sim-db`
5. Wait for first deploy (~5–10 min on free tier)

### Render environment variables (career-sim-api → Environment)

| Key | Value | Notes |
|-----|-------|-------|
| `CORS_ORIGIN` | `https://YOUR-APP.vercel.app` | **Required** — no trailing slash |
| `OPENAI_API_KEY` | `sk-...` | Optional; enables live AI mentor/portfolio/interview |
| `PUBLIC_API_URL` | `https://career-sim-api.onrender.com` | Your actual Render URL |

`JWT_SECRET` and `DATABASE_URL` are set automatically by the Blueprint.

### Verify API

```powershell
curl https://career-sim-api.onrender.com/api/health
```

Expected JSON includes `"phase": 10`, `"database": "connected"`, `"deploy": "production_ready"`.

---

## Step 3 — Vercel (web)

1. https://vercel.com → **Add New** → **Project** → import GitHub repo
2. **Root Directory:**
   - Option A repo: `apps/web`
   - Option B monorepo: `career-simulator/apps/web`
3. Framework: **Next.js** (auto)
4. Build/install commands come from `apps/web/vercel.json` (monorepo-aware)

### Vercel environment variables (Production)

| Key | Value |
|-----|-------|
| `NEXT_PUBLIC_API_URL` | `https://career-sim-api.onrender.com` |
| `NEXT_PUBLIC_APP_NAME` | `AI Career Transition Simulator` |

5. **Deploy**
6. Copy your live URL (e.g. `https://career-simulator.vercel.app`)

---

## Step 4 — Wire CORS (do this last)

Back on Render → **career-sim-api** → **Environment**:

```
CORS_ORIGIN=https://your-app.vercel.app,https://your-app-git-main-youruser.vercel.app
```

Comma-separated preview + production URLs. **Redeploy** the API service after saving.

---

## Step 5 — Smoke test production

1. Open Vercel URL → **Register**
2. Upload resume → job match
3. Run one simulation task
4. Generate portfolio
5. Start mock interview
6. Open AI mentor sidebar (needs `OPENAI_API_KEY` on Render)

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| CORS error in browser | Set `CORS_ORIGIN` on Render to exact Vercel origin |
| API 502 / cold start | Free Render sleeps; first request may take ~30s |
| `database: disconnected` | Check `DATABASE_URL` linked to `career-sim-db` |
| Mentor generic replies | Add `OPENAI_API_KEY` on Render |
| Vercel build fails | Confirm root dir + `vercel.json` install from monorepo root |

---

## Phase 11 — CI on every push

After push, GitHub Actions (`.github/workflows/ci.yml`) runs `npm run build` + Docker smoke build on `main`.

See `PHASE-11.md` for details.

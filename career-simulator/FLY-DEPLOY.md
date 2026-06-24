# Fly.io backend deploy — career-simulator API + Postgres

Replaces Render for the Express API. **Web stays on Vercel.**

---

## Architecture

```
Vercel (Next.js)  →  HTTPS  →  Fly.io (Docker API)  →  Fly Postgres
```

**API URL (after deploy):** `https://career-simulator-api.fly.dev`

---

## Prerequisites

1. [Fly.io account](https://fly.io/app/sign-up) (free tier works)
2. [Fly CLI](https://fly.io/docs/flyctl/install/) installed

**Windows (PowerShell):**
```powershell
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

3. Login:
```powershell
flyctl auth login
```

---

## Step 1 — Create Postgres database

```powershell
cd career-simulator
flyctl postgres create --name career-sim-db --region iad --initial-cluster-size 1 --vm-size shared-cpu-1x --volume-size 1
```

Save the connection details Fly prints.

---

## Step 2 — Launch the API app (first time only)

```powershell
cd career-simulator
flyctl launch --no-deploy --copy-config --name career-simulator-api
```

If the app name is taken, pick another name and update:
- `fly.toml` → `app = 'your-name'`
- `PUBLIC_API_URL` in `fly.toml`
- Vercel `NEXT_PUBLIC_API_URL`

---

## Step 3 — Attach database + secrets

```powershell
flyctl postgres attach career-sim-db --app career-simulator-api
```

Set secrets (generate a long random string for JWT):

```powershell
flyctl secrets set JWT_SECRET="your-long-random-secret-min-32-chars" --app career-simulator-api
```

Optional:
```powershell
flyctl secrets set OPENAI_API_KEY="sk-..." --app career-simulator-api
flyctl secrets set CLERK_SECRET_KEY="sk_live_..." --app career-simulator-api
```

`DATABASE_URL` is set automatically when you attach Postgres.

---

## Step 4 — Deploy

```powershell
cd career-simulator
flyctl deploy
```

Wait ~3–5 minutes. First request after idle may take a few seconds (auto-start).

---

## Step 5 — Verify API

```powershell
curl https://career-simulator-api.fly.dev/api/health
```

Expect: `"ok": true`, `"database": "connected"`, `"deploy": "production_ready"`

---

## Step 6 — Update Vercel

Vercel → **career-simulator** → **Environment Variables**:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://career-simulator-api.fly.dev` |

**Redeploy** Vercel (Deployments → Redeploy).

---

## Step 7 — Smoke test

1. https://career-simulator-ranjinigirish.vercel.app
2. Register → resume → dashboard
3. Home should show **API online**

---

## Useful commands

```powershell
flyctl status                    # app status
flyctl logs                      # live logs
flyctl secrets list              # env secrets
flyctl postgres connect -a career-sim-db   # psql
flyctl deploy                    # redeploy after code changes
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| CORS errors | Update `CORS_ORIGIN` in `fly.toml` or `flyctl secrets set CORS_ORIGIN=...` then redeploy |
| `database: disconnected` | Run `flyctl postgres attach career-sim-db --app career-simulator-api` |
| App name taken | Change `app` in `fly.toml`, redeploy |
| Cold start slow | Normal on free tier — wait 5–10s on first request |
| Health check fails | `flyctl logs` — migrations run on startup |

---

## Local Docker smoke test (optional)

```powershell
cd career-simulator
npm run build
docker build -f Dockerfile.api -t career-sim-api .
docker run --rm -p 4000:4000 -e DATABASE_URL=postgresql://... -e JWT_SECRET=test career-sim-api
```

---

## Legacy Render

`render.yaml` is kept for reference but **Fly.io is the recommended backend** going forward.

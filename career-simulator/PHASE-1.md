# Phase 1 — Project setup & folder structure

## What this phase delivers

A runnable monorepo skeleton: frontend, backend, shared types, and local PostgreSQL — ready for authentication and features in Phase 2+.

---

## File structure (key files)

```
career-simulator/
├── package.json              # Root scripts: dev, build, db:up
├── docker-compose.yml        # Postgres on localhost:5433
├── .env.example
│
├── packages/shared/
│   └── src/index.ts          # SIM_ROLES, DEVELOPMENT_PHASES, HealthResponse type
│
├── apps/api/
│   └── src/
│       ├── index.ts          # Express app entry
│       ├── config/env.ts     # Zod-validated env vars
│       ├── db/pool.ts        # pg Pool + health check
│       ├── routes/health.ts  # GET /api/health
│       └── middleware/error-handler.ts
│
└── apps/web/
    └── src/
        ├── app/
        │   ├── layout.tsx    # Theme + AppShell
        │   ├── page.tsx      # Landing + roadmap
        │   ├── journey/      # Wizard preview
        │   └── roles/        # Simulation modules preview
        ├── components/
        │   ├── ui/           # ShadCN-style Button, Card, Badge, Progress
        │   └── layout/       # AppShell, MentorSidebar (Phase 5 placeholder)
        └── lib/
            ├── utils.ts      # cn() helper
            └── api-client.ts # fetchHealth()
```

---

## How each piece works

### Shared package (`@career-sim/shared`)

Single source of truth for role definitions and API response types. Both web and api import from here so types stay in sync.

### Express API

- Loads env from root `.env`
- `GET /api/health` returns `{ ok, service, phase, database }`
- Database check runs `SELECT 1` if `DATABASE_URL` is set; otherwise `"skipped"`

### Next.js web

- **AppShell:** top nav + main content + right **Mentor sidebar** (placeholder for Phase 5)
- **ThemeToggle:** dark/light via `next-themes`
- **SystemStatus:** server component that calls the API health endpoint on the home page

---

## How to test Phase 1

### Test 1 — API only

```powershell
cd career-simulator
npm install
copy .env.example .env
npm run dev:api
```

Open http://localhost:4000/api/health — expect JSON with `"phase": 1`.

### Test 2 — API + database

```powershell
npm run db:up
npm run dev:api
```

Health response should show `"database": "connected"`.

### Test 3 — Full stack

```powershell
npm run dev
```

1. Open http://localhost:3000 — landing page loads  
2. **System status** card shows API online (and DB if Docker is running)  
3. Visit `/journey` — 6-step wizard preview  
4. Visit `/roles` — four simulation modules listed  
5. Toggle dark/light mode (top right)  
6. On large screens, mentor sidebar appears on the right  

### Test 4 — Build

```powershell
npm run build
```

All three packages should compile without errors.

---

## Environment variables (Phase 1)

| Variable | Required now | Purpose |
|----------|--------------|---------|
| `PORT` | No (default 4000) | API port |
| `DATABASE_URL` | No | Postgres connection |
| `CORS_ORIGIN` | No | Default `http://localhost:3000` |
| `OPENAI_API_KEY` | No | Phase 5 |
| `JWT_SECRET` | No | Phase 2 |

---

## Next phase preview

**Phase 2 — Authentication**

- User registration & login
- JWT access tokens
- Protected API routes
- Auth UI (sign up / sign in)
- PostgreSQL `users` table + migrations

---

## Confirm to continue

Reply **"continue Phase 2"** (or **"yes"**) when you want JWT authentication implemented.

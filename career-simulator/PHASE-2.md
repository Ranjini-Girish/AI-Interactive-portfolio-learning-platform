# Phase 2 — JWT authentication

## What this phase delivers

Users can **create an account**, **sign in**, and access **protected routes** with JWT bearer tokens. Passwords are hashed with bcrypt; user records live in PostgreSQL.

---

## New & updated files

```
career-simulator/
├── apps/api/src/
│   ├── db/migrations/001_users.sql    # users table
│   ├── db/migrate.ts                  # runs SQL on startup
│   ├── repositories/user-repository.ts
│   ├── services/auth-service.ts       # register, login, getUser
│   ├── services/jwt-service.ts        # sign + verify JWT
│   ├── middleware/auth.ts             # requireAuth
│   └── routes/auth.ts                 # /api/auth/*
│
├── apps/web/src/
│   ├── app/login/page.tsx
│   ├── app/register/page.tsx
│   ├── app/dashboard/page.tsx         # protected
│   ├── components/providers/auth-provider.tsx
│   ├── components/auth/auth-guard.tsx
│   └── lib/auth-storage.ts            # JWT in localStorage
│
└── packages/shared/src/auth.ts        # AuthResponse, UserPublic types
```

---

## API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/register` | No | `{ email, password, fullName }` → `{ token, user }` |
| POST | `/api/auth/login` | No | `{ email, password }` → `{ token, user }` |
| GET | `/api/auth/me` | Bearer JWT | Current user profile |
| GET | `/api/auth/dashboard` | Bearer JWT | Protected dashboard stub |
| GET | `/api/health` | No | Now reports `phase: 2`, `auth: ready` |

### Example — register (curl)

```powershell
curl -X POST http://localhost:4000/api/auth/register `
  -H "Content-Type: application/json" `
  -d '{"email":"demo@example.com","password":"password123","fullName":"Demo User"}'
```

### Example — protected route

```powershell
$token = "<paste token from register response>"
curl http://localhost:4000/api/auth/me -H "Authorization: Bearer $token"
```

---

## How it works (plain English)

1. **Register** — password is hashed (never stored plain text), user row inserted, JWT issued.
2. **Login** — email lookup + bcrypt compare, JWT issued on success.
3. **JWT** — contains user id (`sub`) and email; expires in 7 days (configurable via `JWT_EXPIRES_IN`).
4. **Protected routes** — `requireAuth` middleware reads `Authorization: Bearer …`, verifies token, loads user from DB.
5. **Frontend** — token saved in `localStorage`; `AuthProvider` restores session on page load via `/api/auth/me`.

---

## How to test Phase 2

### 1. Start PostgreSQL

```powershell
cd career-simulator
npm run db:up
copy .env.example .env
```

Ensure `.env` has:

```
DATABASE_URL=postgresql://career_sim:career_sim_dev@localhost:5433/career_simulator
JWT_SECRET=your-local-dev-secret-at-least-32-chars
```

### 2. Run both servers

```powershell
npm run dev
```

API log should show: `[db] Applied migration: 001_users.sql`

### 3. Web UI flow

1. http://localhost:3000/register — create account  
2. Redirects to **Dashboard**  
3. Header shows **Dashboard** nav + sign-out  
4. Sign out → visit `/dashboard` → redirects to `/login`  
5. Sign in again with same credentials  

### 4. Health check

http://localhost:4000/api/health → `"phase": 2`, `"auth": "ready"`, `"database": "connected"`

---

## Security notes (demo vs production)

| Topic | Phase 2 choice |
|-------|----------------|
| Token storage | `localStorage` (simple for learning app) |
| Password rules | Min 8 characters |
| Hashing | bcrypt, 12 rounds |
| Production hardening | httpOnly cookies, refresh tokens — later phase |

---

## Next phase preview

**Phase 3 — Resume parser + analyzer**

- Upload PDF/DOCX/text resume  
- Extract skills, experience, projects  
- Generate learning roadmap + job match score  
- Sample resumes bundled in app  

---

## Confirm to continue

Reply **"continue Phase 3"** when you want the resume intelligence engine.

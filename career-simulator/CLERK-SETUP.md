# Clerk authentication setup

Clerk replaces the built-in email/password forms when you set the env vars below.
Without them, the app keeps using **JWT auth** (register/login pages as before).

---

## How it works

```
User → Clerk sign-in (Vercel) → Clerk session token
     → Express API verifies token → links/creates row in PostgreSQL `users`
```

- **Frontend:** `@clerk/nextjs` (SignIn / SignUp, middleware, session)
- **Backend:** `@clerk/backend` verifies Bearer tokens on `/api/*` routes
- **Database:** migration `008_clerk.sql` adds `clerk_id` column

---

## Step 1 — Create a Clerk application

1. Go to **https://dashboard.clerk.com** and sign up / log in
2. Click **Create application**
3. Name it e.g. `Career Transition Simulator`
4. Choose sign-in methods (Email + Google is a good default)
5. Click **Create application**

---

## Step 2 — Copy API keys

In Clerk Dashboard → **Configure** → **API keys**:

| Key | Example prefix | Where it goes |
|-----|----------------|---------------|
| **Publishable key** | `pk_test_...` / `pk_live_...` | Vercel: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` |
| **Secret key** | `sk_test_...` / `sk_live_...` | **Render API** + **Vercel** (see below) |

---

## Step 3 — Configure Clerk URLs

Clerk Dashboard → **Configure** → **Paths** (or **Domains**):

| Setting | Local | Production |
|---------|-------|------------|
| **Sign-in URL** | `http://localhost:3000/login` | `https://career-simulator-ranjinigirish.vercel.app/login` |
| **Sign-up URL** | `http://localhost:3000/register` | `https://YOUR-VERCEL-URL/register` |
| **After sign-in** | `http://localhost:3000/dashboard` | `https://YOUR-VERCEL-URL/dashboard` |
| **After sign-up** | `http://localhost:3000/dashboard` | `https://YOUR-VERCEL-URL/dashboard` |

Add your Vercel preview URL if you use branch deploys.

---

## Step 4 — Local `.env`

In `career-simulator/.env`:

```env
# Existing
DATABASE_URL=postgresql://career_sim:career_sim_dev@localhost:5433/career_simulator
NEXT_PUBLIC_API_URL=http://localhost:4000

# Clerk — add these
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_xxxxxxxx
CLERK_SECRET_KEY=sk_test_xxxxxxxx
```

Restart dev servers:

```powershell
cd career-simulator
npm run db:up
npm run dev
```

Open http://localhost:3000/login — you should see **Clerk’s** sign-in UI (not the old email form).

---

## Step 5 — Render (API)

**career-sim-api** → **Environment** → add:

```
CLERK_SECRET_KEY=sk_live_xxxxxxxx
```

Use the **same secret key** as in Clerk (test key for staging, live key for production).

Redeploy the API. Migrations add `clerk_id` automatically on startup.

---

## Step 6 — Vercel (web)

Project **career-simulator** → **Settings** → **Environment Variables**:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_live_...` |
| `CLERK_SECRET_KEY` | `sk_live_...` |
| `NEXT_PUBLIC_API_URL` | `https://career-sim-api.onrender.com` |

Redeploy Vercel after saving.

---

## Step 7 — Verify

1. Open your Vercel URL → **Sign in** (Clerk UI)
2. Complete sign-up / sign-in
3. Go to **Dashboard** — data should load
4. Optional API check (with Clerk session token from browser devtools):

```bash
curl https://YOUR-API.onrender.com/api/auth/me \
  -H "Authorization: Bearer YOUR_CLERK_SESSION_TOKEN"
```

---

## Inviting collaborators / users

| Who | How |
|-----|-----|
| **App users** | Share your Vercel URL — they sign up via Clerk |
| **Clerk dashboard admins** | Clerk → **Organization settings** → invite team |
| **Vercel deploy access** | Vercel team invite (separate from Clerk) |

Clerk free tier includes thousands of MAUs — fine for demos and small launches.

---

## Switching back to JWT-only

Remove or comment out:

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `CLERK_SECRET_KEY`

Redeploy. The app falls back to `/login` and `/register` email forms.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Still see old login form | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` missing on Vercel — redeploy |
| API 401 after Clerk sign-in | Set `CLERK_SECRET_KEY` on **Render** (not just Vercel) |
| Clerk redirect loop | Match sign-in/sign-up URLs in Clerk dashboard to your Vercel domain |
| User has no email in Clerk | Require email in Clerk sign-in settings |
| Existing JWT users | Same email links to Clerk account on first Clerk sign-in |

---

## Files changed for Clerk

| Area | Files |
|------|-------|
| API | `services/clerk-auth.ts`, `middleware/auth.ts`, `008_clerk.sql` |
| Web | `middleware.ts`, `clerk-app-provider.tsx`, `auth-provider.tsx`, login/register pages |
| Config | `.env.example`, `render.yaml`, `CLERK-SETUP.md` |

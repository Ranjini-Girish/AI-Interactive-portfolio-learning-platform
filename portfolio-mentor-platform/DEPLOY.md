# Deploy to Vercel

Production build verified: `npm run build` in this folder must pass before deploy.

## Option A — Vercel website (recommended)

1. Push this repo to GitHub (monorepo root: `Airdawg_terminal` or your fork).
2. Go to [vercel.com/new](https://vercel.com/new) and sign in.
3. **Import** your GitHub repository.
4. **Critical:** set **Root Directory** to `portfolio-mentor-platform` (not the repo root).
5. Framework: **Next.js** (auto-detected). Build command: `npm run build`. Output: default.
6. Click **Deploy**.

Your live URL will look like: `https://portfolio-mentor-platform-xxx.vercel.app`

### After first deploy — set these pages

| Page | Path |
|------|------|
| Home | `/` |
| Start here (beginners) | `/start` |
| Try apps | `/portfolio` |
| Learning paths | `/build` |

## Option B — Vercel CLI

```powershell
cd portfolio-mentor-platform
npm run build
npx vercel login
npx vercel
npx vercel --prod
```

If you see `token is not valid`, run `npx vercel login` first (opens browser).

## Environment variables

In Vercel → Project → Settings → Environment Variables, add:

| Variable | Required | Purpose |
|----------|----------|---------|
| `RESEND_API_KEY` | Optional | Contact form sends email |
| `CONTACT_TO_EMAIL` | Optional | Inbox (default: Racgowda18@gmail.com) |
| `CONTACT_FROM_EMAIL` | Optional | Verified sender in Resend |
| `OPENAI_API_KEY` | Optional | Live AI mentor in Build Lab |
| `OPENAI_MODEL` | Optional | Default `gpt-4o-mini` |

Without `RESEND_API_KEY`, the contact form returns a **mailto** fallback (still usable).

## 4. CLI deploy (alternative)

```powershell
npm i -g vercel
cd portfolio-mentor-platform
vercel
vercel --prod
```

## 5. Portfolio demo apps (P01–P03)

The main site deploys to Vercel. **Flask/Python demos** run separately:

| App | Suggested host |
|-----|----------------|
| P01, P02, P03 | Railway, Render, or Fly.io |
| Or locally | Keep localhost links in Build Lab |

After deploying demos, set public URLs in Vercel env:

```
NEXT_PUBLIC_DEMO_P01_URL=https://your-p01.vercel.app
NEXT_PUBLIC_DEMO_P02_URL=https://your-p02.onrender.com
```

## 6. Custom domain

Vercel → Settings → Domains → add e.g. `ranjinigowda.dev`

## Notes

- Build Lab progress stays in **browser localStorage** (per device).
- `allow_internet`-style offline rules do not apply here — this is your portfolio site, not Terminus tasks.

# Phase 11 — CI/CD (GitHub Actions)

Automated build verification on every push to `main` / `master` and on pull requests.

## What was added

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | Build shared + API + web; Docker API smoke build |
| `scripts/pre-deploy.ps1` | Local pre-push validation |
| `DEPLOY-RUNBOOK.md` | Copy/paste deploy checklist |

## CI pipeline

```
push/PR → checkout → Node 22 → npm ci → npm run build → docker build Dockerfile.api
```

Fails fast if TypeScript, Next.js, or Docker packaging breaks before you deploy.

## Local equivalent

```powershell
cd career-simulator
.\scripts\pre-deploy.ps1
```

## After enabling CI

1. Push to GitHub (dedicated `career-simulator` repo recommended)
2. **Actions** tab → confirm green build
3. Proceed with Render + Vercel per `DEPLOY-RUNBOOK.md`

## Optional next phases (not implemented)

- Playwright E2E (register → resume → simulation)
- Preview deploy env sync (Vercel + Render preview URLs)
- Sentry / structured logging
- Email verification for auth

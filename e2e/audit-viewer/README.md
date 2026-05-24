# Revision Audit Viewer

Next.js dashboard for **live revision E2E flows**. Reads `e2e/audit/revision-runs.jsonl`, `revision-*-latest.log`, and context JSON files.

## Run

```powershell
cd e2e/audit-viewer
npm install
npm run dev
```

Open http://localhost:3200

## Pages

| Route | Purpose |
|-------|---------|
| `/` | Dashboard — all runs + latest per-task logs (auto-refresh + SSE) |
| `/tasks/{slug}` | Visual workflow + live tail of `revision-{slug}-latest.log` |
| `/runs/{runId}` | Single jsonl run with 8-phase workflow timeline |
| `/live` | SSE stream of new `revision-runs.jsonl` events |

## Env

Optional override for audit directory:

```powershell
$env:AUDIT_DIR = 'C:\Users\gengi\Projects\Airdawg_terminal\e2e\audit'
```

## Workflow phases

Open revision → Extract feedback → Swap zip → Upload → Rubric → Static checks → Submit → Verify

Mapped from Playwright steps in `e2e/lib/revision-flow.ts` / `flow-audit-log.ts`.

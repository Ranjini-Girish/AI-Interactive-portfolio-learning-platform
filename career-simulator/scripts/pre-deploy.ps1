# Pre-deploy checks — run from career-simulator/ before pushing to GitHub
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> npm install" -ForegroundColor Cyan
npm install

Write-Host "==> npm run build" -ForegroundColor Cyan
npm run build

Write-Host "==> Docker API build (optional smoke)" -ForegroundColor Cyan
docker build -f Dockerfile.api -t career-sim-api:local .

Write-Host ""
Write-Host "OK — ready to push. Next:" -ForegroundColor Green
Write-Host "  1. GitHub: push this folder (dedicated repo recommended)"
Write-Host "  2. Render: New Blueprint -> render.yaml"
Write-Host "  3. Vercel: root career-simulator/apps/web, set NEXT_PUBLIC_API_URL"
Write-Host "  4. Render env: CORS_ORIGIN = your Vercel URL"
Write-Host ""
Write-Host "See PHASE-10.md and DEPLOY-RUNBOOK.md for full steps."

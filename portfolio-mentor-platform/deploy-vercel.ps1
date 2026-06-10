# Deploy portfolio-mentor-platform to Vercel (production)
# Prerequisite: run once — npx vercel login

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Building..." -ForegroundColor Cyan
npm run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`nDeploying to Vercel (production)..." -ForegroundColor Green
npx vercel --prod --yes
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nIf login failed, run: npx vercel login" -ForegroundColor Yellow
    exit $LASTEXITCODE
}

Write-Host "`nDone. Copy the Production URL from the output above." -ForegroundColor Green

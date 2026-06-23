# Deploy backend to Render — run from repo root after Render login OR use Blueprint in browser

Write-Host ""
Write-Host "=== Career Simulator — Render backend deploy ===" -ForegroundColor Cyan
Write-Host ""

$blueprintUrl = "https://dashboard.render.com/select-repo?type=blueprint"
Write-Host "OPTION A (easiest): Blueprint in browser" -ForegroundColor Green
Write-Host "  1. Open: $blueprintUrl"
Write-Host "  2. Connect repo: AI-Interactive-portfolio-learning-platform"
Write-Host "  3. Branch: main  |  Blueprint path: render.yaml"
Write-Host "  4. Click Deploy Blueprint"
Write-Host "  5. Wait ~10-15 min until career-sim-api shows Live"
Write-Host ""
Write-Host "OPTION B: Render CLI (after login)" -ForegroundColor Green
Write-Host "  render login"
Write-Host "  render blueprints validate render.yaml"
Write-Host "  (Then use Blueprint in dashboard — CLI validates config only)"
Write-Host ""
Write-Host "After deploy, verify:" -ForegroundColor Yellow
Write-Host "  https://career-sim-api.onrender.com/api/health"
Write-Host ""
Write-Host "Beta app (refresh after API is live):" -ForegroundColor Yellow
Write-Host "  https://career-simulator-sandy.vercel.app"
Write-Host ""

$open = Read-Host "Open Render Blueprint in browser now? (y/n)"
if ($open -eq 'y') {
    Start-Process $blueprintUrl
}

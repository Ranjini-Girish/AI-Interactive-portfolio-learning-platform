# One-click Fly.io deploy helper
$fly = Get-Command fly -ErrorAction SilentlyContinue
if (-not $fly) {
  Write-Host "Install Fly CLI first:" -ForegroundColor Yellow
  Write-Host '  powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"'
  Write-Host ""
  Write-Host "Then: fly auth login"
  exit 1
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host ""
Write-Host "=== Fly.io backend deploy ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Full guide: FLY-DEPLOY.md"
Write-Host ""
Write-Host "Quick commands (run in career-simulator/):"
Write-Host "  fly auth login"
Write-Host "  fly postgres create --name career-sim-db --region iad --initial-cluster-size 1 --vm-size shared-cpu-1x --volume-size 1"
Write-Host "  fly launch --no-deploy --copy-config --name career-simulator-api"
Write-Host "  fly postgres attach career-sim-db --app career-simulator-api"
Write-Host "  fly secrets set JWT_SECRET=<long-random-string>"
Write-Host "  fly deploy"
Write-Host ""
Write-Host "Verify: https://career-simulator-api.fly.dev/api/health" -ForegroundColor Yellow
Write-Host "Vercel: set NEXT_PUBLIC_API_URL to same host" -ForegroundColor Yellow
Write-Host ""

$run = Read-Host "Run fly deploy now? (y/n)"
if ($run -eq 'y') {
  fly deploy
}

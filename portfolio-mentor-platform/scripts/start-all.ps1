# Start the full Ranjini portfolio stack (website + P01 + P02 + P03)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/start-all.ps1

$ErrorActionPreference = "Stop"
$PlatformRoot = Split-Path -Parent $PSScriptRoot
$Root = Split-Path -Parent $PlatformRoot

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")

$Node = Get-Command node -ErrorAction SilentlyContinue
$Npm = Get-Command npm -ErrorAction SilentlyContinue
$Py = Get-Command python -ErrorAction SilentlyContinue

if (-not $Node -or -not $Npm) { Write-Error "Node.js not found. Install from https://nodejs.org"; exit 1 }
if (-not $Py) { Write-Error "Python not found. Install from https://python.org"; exit 1 }

Write-Host "=== Portfolio stack setup & start ===" -ForegroundColor Cyan
Write-Host "Root: $Root"

function Ensure-Venv($BackendDir) {
    $venv = Join-Path $BackendDir ".venv"
    if (-not (Test-Path $venv)) {
        Write-Host "Creating venv: $BackendDir"
        Push-Location $BackendDir
        python -m venv .venv
        & ".\.venv\Scripts\pip.exe" install -r requirements.txt -q
        Pop-Location
    } elseif (-not (Test-Path "$venv\Scripts\uvicorn.exe") -and -not (Test-Path "$venv\Scripts\flask.exe")) {
        Push-Location $BackendDir
        & ".\.venv\Scripts\pip.exe" install -r requirements.txt -q
        Pop-Location
    }
}

function Ensure-Npm($Dir) {
    if (-not (Test-Path (Join-Path $Dir "node_modules"))) {
        Write-Host "npm install: $Dir"
        Push-Location $Dir
        npm install --silent
        Pop-Location
    }
}

# --- Install dependencies once ---
Ensure-Npm "$Root\portfolio-mentor-platform"
Ensure-Npm "$Root\apps\p01-customer-segmentation\frontend"
Ensure-Npm "$Root\apps\p02-churn-api\frontend"
Ensure-Npm "$Root\apps\p03-recommendations\frontend"

Ensure-Venv "$Root\apps\p01-customer-segmentation\backend"
Ensure-Venv "$Root\apps\p02-churn-api\backend"
Ensure-Venv "$Root\apps\p03-recommendations\backend"

# P02 model
$p02Art = "$Root\apps\p02-churn-api\backend\artifacts\model.joblib"
if (-not (Test-Path $p02Art)) {
    Write-Host "Training P02 churn model..."
    Push-Location "$Root\apps\p02-churn-api\backend"
    & ".\.venv\Scripts\python.exe" train.py
    Pop-Location
}

# P03 seed
$p03Db = "$Root\apps\p03-recommendations\backend\reco.db"
if (-not (Test-Path $p03Db)) {
    Write-Host "Seeding P03 recommendations..."
    Push-Location "$Root\apps\p03-recommendations\backend"
    & ".\.venv\Scripts\python.exe" seed.py
    Pop-Location
}

# --- Start servers in background jobs ---
Write-Host "`nStarting servers..." -ForegroundColor Green

$jobs = @(
    @{
        Name = "website-3200"
        Dir  = "$Root\portfolio-mentor-platform"
        Cmd  = "npm run dev"
    }
    @{
        Name = "p01-api-8000"
        Dir  = "$Root\apps\p01-customer-segmentation\backend"
        Cmd  = ".\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8000"
    }
    @{
        Name = "p01-ui-5173"
        Dir  = "$Root\apps\p01-customer-segmentation\frontend"
        Cmd  = "npm run dev"
    }
    @{
        Name = "p02-api-8001"
        Dir  = "$Root\apps\p02-churn-api\backend"
        Cmd  = ".\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8001"
    }
    @{
        Name = "p02-ui-5174"
        Dir  = "$Root\apps\p02-churn-api\frontend"
        Cmd  = "npm run dev"
    }
    @{
        Name = "p03-api-8002"
        Dir  = "$Root\apps\p03-recommendations\backend"
        Cmd  = ".\.venv\Scripts\python.exe app.py"
    }
    @{
        Name = "p03-ui-5175"
        Dir  = "$Root\apps\p03-recommendations\frontend"
        Cmd  = "npm run dev"
    }
)

$logDir = Join-Path $Root "portfolio-mentor-platform\.run-logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

foreach ($j in $jobs) {
    $logFile = Join-Path $logDir "$($j.Name).log"
    $sb = @"
Set-Location '$($j.Dir)'
`$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
$($j.Cmd) 2>&1 | Tee-Object -FilePath '$logFile'
"@
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $sb -WindowStyle Minimized
    Write-Host "  started $($j.Name)" -ForegroundColor DarkGray
    Start-Sleep -Milliseconds 800
}

Write-Host "`n=== Ready ===" -ForegroundColor Green
Write-Host "  Website:     http://localhost:3200"
Write-Host "  P01 Seg:     http://localhost:5173  (API :8000)"
Write-Host "  P02 Churn:   http://localhost:5174  (API :8001)"
Write-Host "  P03 Shop:    http://localhost:5175  (API :8002)"
Write-Host "`nOpen http://localhost:3200 in your browser."
Write-Host "Logs: $logDir"
Write-Host "To stop: close the minimized PowerShell windows."

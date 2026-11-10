<#
.SYNOPSIS
  Start the whole app for local development in one step.

  1. Checks the prerequisites: the Python environment, the .env file, Node.js and the
     frontend packages.
  2. Checks that the database in DATABASE_URL is reachable and fully migrated (it never
     runs migrations itself - scripts\migrate.ps1 does).
  3. Starts the backend (start-backend.ps1) and the frontend (start-frontend.ps1) in the
     background, waits until both answer, and prints their URLs and log files.
  4. Keeps running until you press Ctrl+C, then stops the servers it started. If one of
     them exits on its own, the other is stopped too.

  A backend or frontend that is already running from the start scripts is reused and
  left running. Only processes recorded in .run\ by this run are stopped - never other
  Python or Node programs. -Detach starts the servers and returns; stop them later with
  scripts\stop-dev.ps1. Secrets from .env are never printed.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Detach
  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -BackendPort 8001 -FrontendPort 5174
#>
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$Detach,
    [switch]$SkipDbCheck
)

. "$PSScriptRoot\_common.ps1"

# ------------------------------------------------------------------ prerequisites
Write-Step "Checking prerequisites"
Assert-Venv
Write-Ok "Python environment: $VenvDir"
Assert-EnvFile
if (Test-Path (Join-Path $BackendDir ".env")) { Write-Ok "Configuration: backend\.env (overrides .env)" } else { Write-Ok "Configuration: .env" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail "Node.js was not found. Install the LTS release from https://nodejs.org/ and open a new terminal." }
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) { Fail "Frontend packages are missing. Run scripts\install-frontend.ps1 first." }
Write-Ok "Node.js $((& node --version).Trim())"

# ------------------------------------------------------------------ database
if ($SkipDbCheck) {
    Write-Host "    Skipping the database check (-SkipDbCheck)." -ForegroundColor Yellow
} else {
    Write-Step "Checking the database (DATABASE_URL; the password is never shown)"
    Push-Location $BackendDir
    try { $dbReport = @(& $VenvPython (Join-Path $PSScriptRoot "check_db.py")); $dbCode = $LASTEXITCODE } finally { Pop-Location }
    $dbReport | ForEach-Object { Write-Host $_ }
    if ($dbCode -ne 0) { Fail "The database is not reachable. scripts\check-db.ps1 lists what to check." }
    if ($dbReport -match "not migrated yet|behind the latest") { Fail "The database schema is not up to date. Run scripts\migrate.ps1, then start again." }
    Write-Ok "Database reachable and migrated"
}

# ------------------------------------------------------------------ start
# The frontend dev server proxies /api to the backend; point it at the chosen port.
if (-not $env:AGRIGUARD_API_URL) { $env:AGRIGUARD_API_URL = "http://127.0.0.1:$BackendPort" }

$started = New-Object System.Collections.Generic.List[string]

function Stop-Started {
    foreach ($name in @($started)) {
        switch (Stop-DevProcess $name) {
            "stopped"         { Write-Ok "$name stopped" }
            "already-stopped" { Write-Ok "$name had already stopped" }
            "failed"          { Write-Host "    Could not stop $name; run scripts\stop-dev.ps1" -ForegroundColor Red }
        }
    }
    $started.Clear()
}

$services = @(
    @{ Name = "backend";  Script = "start-backend.ps1";  Port = $BackendPort },
    @{ Name = "frontend"; Script = "start-frontend.ps1"; Port = $FrontendPort }
)
foreach ($service in $services) {
    if (Get-RecordedProcess $service.Name) {
        Write-Ok "$($service.Name) is already running (started earlier; left as it is)"
        continue
    }
    $global:LASTEXITCODE = 0
    try {
        & (Join-Path $PSScriptRoot $service.Script) -Port $service.Port
        $code = $LASTEXITCODE
    } catch {
        Write-Host "    $($_.Exception.Message)" -ForegroundColor Red
        $code = 1
    }
    if (Get-ProcessRecord $service.Name) { $started.Add($service.Name) }
    if ($code -ne 0) {
        Write-Host "    $($service.Name) did not start. Stopping what this script started." -ForegroundColor Red
        Stop-Started
        exit 1
    }
}

# ------------------------------------------------------------------ summary
$health = $null
try { $health = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/health" -TimeoutSec 10 } catch { }
Write-Host ""
Write-Host "AgriGuard AI is running" -ForegroundColor Green
Write-Host "  App (frontend)   http://127.0.0.1:$FrontendPort"
Write-Host "  API (backend)    http://127.0.0.1:$BackendPort"
Write-Host "  API docs         http://127.0.0.1:$BackendPort/api/docs"
Write-Host "  Health check     http://127.0.0.1:$BackendPort/health"
if ($health) {
    $ai = if ($health.ai_service -eq "ok") { "ready" } else { "no trained model - scans answer 503 (see docs\SETUP_AND_RUN.md)" }
    Write-Host "  Status           database=$($health.database), image classifier: $ai"
}
Write-Host "  Logs             $(Join-Path $LogDir 'backend-dev.err.log')"
Write-Host "                   $(Join-Path $LogDir 'frontend-dev.out.log')"

if ($Detach) {
    Write-Host ""
    Write-Host "Running in the background. Stop with: powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1"
    exit 0
}

Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor Cyan
$exitCode = 0
try {
    while ($true) {
        Start-Sleep -Seconds 2
        $gone = @($started | Where-Object { -not (Get-RecordedProcess $_) })
        if ($gone.Count -gt 0) {
            Write-Host ""
            Write-Host "    $($gone -join ', ') stopped unexpectedly - see the logs above." -ForegroundColor Red
            $exitCode = 1
            break
        }
    }
} finally {
    # Runs on Ctrl+C too.
    Write-Host ""
    Write-Step "Stopping the servers started by this script"
    Stop-Started
}
exit $exitCode

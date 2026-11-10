<#
.SYNOPSIS
  Start the FastAPI backend with Uvicorn (no Docker, no NGINX).

  By default it runs in the background, logs to logs\backend-dev.*.log and records
  its process so scripts\stop-dev.ps1 can stop it. -Foreground runs it in this
  window instead (Ctrl+C to stop).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1
  powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1 -Foreground
#>
param(
    [int]$Port = 8000,
    [string]$BindAddress = "127.0.0.1",
    [switch]$NoReload,
    [switch]$Foreground
)

. "$PSScriptRoot\_common.ps1"
Assert-Venv
Assert-EnvFile

if (Get-RecordedProcess "backend") { Fail "The backend is already running (scripts\stop-dev.ps1 stops it)." }
if (Test-PortInUse $Port) { Fail "Port $Port is already in use. Stop that process or pass -Port." }

# --no-proxy-headers: there is no reverse proxy in local development (the Vite dev
# proxy sends no X-Forwarded-For), and uvicorn would otherwise trust that header from
# 127.0.0.1, letting any local process reset its rate-limit bucket by setting it.
$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $BindAddress, "--port", "$Port", "--no-proxy-headers")
if (-not $NoReload) {
    # Watch only source folders, not storage/logs written while serving.
    $uvicornArgs += @("--reload", "--reload-dir", (Join-Path $BackendDir "app"), "--reload-dir", (Join-Path $RepoRoot "ai"))
}

if ($Foreground) {
    Write-Step "Starting backend on http://${BindAddress}:$Port (Ctrl+C to stop)"
    Push-Location $BackendDir
    try { & $VenvPython @uvicornArgs } finally { Pop-Location }
    exit $LASTEXITCODE
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$outLog = Join-Path $LogDir "backend-dev.out.log"
$errLog = Join-Path $LogDir "backend-dev.err.log"

Write-Step "Starting backend on http://${BindAddress}:$Port"
$process = Start-BackgroundCommand $VenvPython $uvicornArgs $BackendDir $outLog $errLog
Save-ProcessRecord "backend" $process

$status = Wait-HttpOk "http://${BindAddress}:$Port/health" 90
if ($status -eq 200) {
    Write-Ok "Backend healthy: http://${BindAddress}:$Port/api/docs"
} elseif ($status -eq 503) {
    Write-Host "    Backend is up but /health reports the database is down (scripts\check-db.ps1)." -ForegroundColor Yellow
} else {
    Write-Host "    Backend did not answer on /health. Last log lines:" -ForegroundColor Red
    Get-Content $errLog -Tail 20 -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "    Logs: $errLog"

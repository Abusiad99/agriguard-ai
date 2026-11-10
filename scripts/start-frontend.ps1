<#
.SYNOPSIS
  Start the React/Vite dev server. It proxies /api and /storage to the backend
  (http://127.0.0.1:8000 by default; set $env:AGRIGUARD_API_URL to change it).

  By default it runs in the background, logs to logs\frontend-dev.*.log and records
  its process so scripts\stop-dev.ps1 can stop it. -Foreground runs it in this
  window instead (Ctrl+C to stop).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start-frontend.ps1
#>
param(
    [int]$Port = 5173,
    [switch]$Foreground
)

. "$PSScriptRoot\_common.ps1"

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) { Fail "Frontend dependencies are missing. Run scripts\install-frontend.ps1 first." }
if (Get-RecordedProcess "frontend") { Fail "The frontend is already running (scripts\stop-dev.ps1 stops it)." }
if (Test-PortInUse $Port) { Fail "Port $Port is already in use. Stop that process or pass -Port." }

$viteArgs = @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$Port")

if ($Foreground) {
    Write-Step "Starting frontend on http://127.0.0.1:$Port (Ctrl+C to stop)"
    Push-Location $FrontendDir
    try { & npm.cmd @viteArgs } finally { Pop-Location }
    exit $LASTEXITCODE
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$outLog = Join-Path $LogDir "frontend-dev.out.log"
$errLog = Join-Path $LogDir "frontend-dev.err.log"

Write-Step "Starting frontend on http://127.0.0.1:$Port"
# Full path: invoked by bare name through cmd.exe, the npm.cmd shim resolves its own
# folder (%~dp0) as the current directory and fails to find npm-cli.js.
$npm = (Get-Command npm.cmd).Source
$process = Start-BackgroundCommand $npm $viteArgs $FrontendDir $outLog $errLog
Save-ProcessRecord "frontend" $process

$status = Wait-HttpOk "http://127.0.0.1:$Port/" 60
if ($status -eq 200) {
    Write-Ok "Frontend running: http://127.0.0.1:$Port"
} else {
    Write-Host "    Frontend did not answer. Last log lines:" -ForegroundColor Red
    Get-Content $outLog, $errLog -Tail 20 -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "    Logs: $outLog"

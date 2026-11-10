<#
.SYNOPSIS
  Stop the backend and frontend dev servers started by start-backend.ps1 /
  start-frontend.ps1 in the background.

  Only processes recorded in .run\ are stopped, and only if their process id still
  belongs to the same process (same start time) - never by name, so other Python or
  Node programs are left alone. Child processes (Uvicorn's reloader, Vite under
  npm) are stopped with them. The database is not touched.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
#>
. "$PSScriptRoot\_common.ps1"

foreach ($name in @("frontend", "backend")) {
    $record = Get-ProcessRecord $name
    if ($null -eq $record) {
        Write-Ok "$name was not started by these scripts"
        continue
    }
    $process = Get-RecordedProcess $name
    if ($null -eq $process) {
        Write-Ok "$name had already stopped"
    } else {
        Write-Step "Stopping $name (pid $($process.Id) and its child processes)"
        & taskkill.exe /PID $process.Id /T /F | Out-Null
        if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
            Fail "Could not stop $name (pid $($process.Id))."
        }
        Write-Ok "$name stopped"
    }
    Remove-ProcessRecord $name
}

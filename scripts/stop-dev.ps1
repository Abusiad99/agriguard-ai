<#
.SYNOPSIS
  Stop the backend and frontend dev servers started by start-backend.ps1 /
  start-frontend.ps1 (or dev.ps1 -Detach) in the background.

  Only processes recorded in .run\ are stopped, and only if their process id still
  belongs to the same process (same start time) - never by name, so other Python or
  Node programs are left alone. Child processes (Uvicorn's reloader, Vite under
  npm) are stopped with them. The database is not touched.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
#>
. "$PSScriptRoot\_common.ps1"

foreach ($name in @("frontend", "backend")) {
    $process = Get-RecordedProcess $name
    if ($null -ne $process) { Write-Step "Stopping $name (pid $($process.Id) and its child processes)" }
    switch (Stop-DevProcess $name) {
        "not-started"     { Write-Ok "$name was not started by these scripts" }
        "already-stopped" { Write-Ok "$name had already stopped" }
        "stopped"         { Write-Ok "$name stopped" }
        "failed"          { Fail "Could not stop $name (pid $($process.Id))." }
    }
}

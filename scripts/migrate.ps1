<#
.SYNOPSIS
  Run Alembic database migrations against DATABASE_URL (from .env).

.PARAMETER Action
  upgrade (default), downgrade, current or history.

.PARAMETER Revision
  Target revision. Defaults to "head" for upgrade. Required for downgrade, e.g. -1
  or 0002; a downgrade can drop data in removed columns, so it is never implicit.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\migrate.ps1
  powershell -ExecutionPolicy Bypass -File scripts\migrate.ps1 -Action current
  powershell -ExecutionPolicy Bypass -File scripts\migrate.ps1 -Action downgrade -Revision 0002
#>
param(
    [ValidateSet("upgrade", "downgrade", "current", "history")]
    [string]$Action = "upgrade",
    [string]$Revision = ""
)

. "$PSScriptRoot\_common.ps1"
Assert-Venv
Assert-EnvFile

$alembicArgs = @("-m", "alembic", "-c", "alembic.ini", $Action)
if ($Action -eq "upgrade") {
    if (-not $Revision) { $Revision = "head" }
    $alembicArgs += $Revision
} elseif ($Action -eq "downgrade") {
    if (-not $Revision) { Fail "A downgrade needs an explicit -Revision (for example -1 or 0002)." }
    $alembicArgs += $Revision
}

Write-Step "alembic $Action $Revision"
Push-Location $BackendDir
try {
    & $VenvPython @alembicArgs
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($code -ne 0) { Fail "Alembic $Action failed (see the output above; scripts\check-db.ps1 tests the connection)." }
Write-Ok "alembic $Action finished"

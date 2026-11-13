<#
.SYNOPSIS
  Back up the PostgreSQL database in DATABASE_URL (from .env) to one file, and check that the
  file is a readable archive. Changes nothing in the database. Run it before every migration.

.PARAMETER OutDir
  Folder for the backup. Default: agriguard-backups in your user folder. It must be outside
  the repository, so a backup can never be committed.

.PARAMETER Container
  Name of the Docker container that runs PostgreSQL (for example agriguard_postgres). Use it
  when the database runs in Docker: pg_dump then runs inside that container. Without it,
  pg_dump and pg_restore from your PostgreSQL installation are used.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\backup-db.ps1
  powershell -ExecutionPolicy Bypass -File scripts\backup-db.ps1 -Container agriguard_postgres
#>
param(
    [string]$OutDir = (Join-Path $HOME "agriguard-backups"),
    [string]$Container = ""
)

. "$PSScriptRoot\_common.ps1"
Assert-Venv
Assert-EnvFile

Write-Step "Backing up the database configured in .env"
$backupArgs = @((Join-Path $PSScriptRoot "backup_db.py"), "--out-dir", $OutDir)
if ($Container) { $backupArgs += @("--container", $Container) }

Push-Location $BackendDir
try { & $VenvPython @backupArgs; $code = $LASTEXITCODE } finally { Pop-Location }
if ($code -ne 0) { Fail "No backup was made. Do not migrate until a backup succeeds." }
Write-Ok "Backup written and readable. Keep it private: it contains all application data."

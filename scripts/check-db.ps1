<#
.SYNOPSIS
  Check that the PostgreSQL database in DATABASE_URL (from .env) is reachable, and
  report its version and current migration revision. Changes nothing.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\check-db.ps1
#>
. "$PSScriptRoot\_common.ps1"
Assert-Venv
Assert-EnvFile

Write-Step "Connecting to the database configured in .env"
Push-Location $BackendDir
try { & $VenvPython (Join-Path $PSScriptRoot "check_db.py"); $code = $LASTEXITCODE } finally { Pop-Location }
if ($code -ne 0) {
    Write-Host ""
    Write-Host "Could not connect. Check that:" -ForegroundColor Yellow
    Write-Host "  - the PostgreSQL service is running (services.msc, or: pg_ctl status -D <data dir>)"
    Write-Host "  - DATABASE_URL in .env has the right host, port, user, password and database"
    Write-Host "  - the role and database exist, e.g. as the postgres superuser:"
    Write-Host "      psql -U postgres -c ""CREATE ROLE agriguard LOGIN PASSWORD 'YOUR_DB_PASSWORD';"""
    Write-Host "      psql -U postgres -c ""CREATE DATABASE agriguard OWNER agriguard;"""
    exit 1
}
Write-Ok "Database reachable"

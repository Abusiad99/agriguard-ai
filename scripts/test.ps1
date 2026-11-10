<#
.SYNOPSIS
  Run the automated checks without Docker: backend pytest, and frontend lint,
  type check, unit tests (Vitest) and production build.

.PARAMETER PostgresUrl
  Also run the database-backed tests and the migration tests against a real
  PostgreSQL database. The database name must end in "_test": every table in it is
  dropped and recreated. Example:
    -PostgresUrl postgresql+psycopg2://agriguard:agriguard@127.0.0.1:5432/agriguard_test

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\test.ps1
#>
param(
    [string]$PostgresUrl = "",
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

. "$PSScriptRoot\_common.ps1"
$failed = @()

if (-not $FrontendOnly) {
    Assert-Venv
    if ($PostgresUrl) {
        $env:AGRIGUARD_TEST_DATABASE_URL = $PostgresUrl
        Write-Step "Backend tests (database tests on PostgreSQL)"
    } else {
        Remove-Item Env:\AGRIGUARD_TEST_DATABASE_URL -ErrorAction SilentlyContinue
        Write-Step "Backend tests (database tests on in-memory SQLite; PostgreSQL-only tests are skipped)"
    }
    Push-Location $BackendDir
    try { & $VenvPython -m pytest -q -p no:cacheprovider; $code = $LASTEXITCODE } finally { Pop-Location }
    if ($code -ne 0) { $failed += "backend tests" }
}

if (-not $BackendOnly) {
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) { Fail "Run scripts\install-frontend.ps1 first." }
    Push-Location $FrontendDir
    try {
        foreach ($script in @("lint", "typecheck", "test", "build")) {
            Write-Step "npm run $script"
            & npm.cmd run $script
            if ($LASTEXITCODE -ne 0) { $failed += "frontend $script" }
        }
    } finally {
        Pop-Location
    }
}

if ($failed.Count -gt 0) { Fail ("Failed: " + ($failed -join ", ")) }
Write-Ok "All checks passed"

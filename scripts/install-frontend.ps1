<#
.SYNOPSIS
  Install the frontend (React/Vite) dependencies with npm.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install-frontend.ps1
#>
. "$PSScriptRoot\_common.ps1"

Write-Step "Checking Node.js 18+ and npm"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail "Node.js was not found. Install the LTS release from https://nodejs.org/ and re-run." }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { Fail "npm was not found (it ships with Node.js)." }
$nodeVersion = (& node --version).TrimStart("v")
if ([version]$nodeVersion -lt [version]"18.0") { Fail "Node.js $nodeVersion is too old; Vite 5 needs 18 or newer." }
Write-Ok "Node.js $nodeVersion, npm $(& npm.cmd --version)"

Push-Location $FrontendDir
try {
    if (Test-Path "package-lock.json") {
        Write-Step "npm ci (exact versions from package-lock.json)"
        & npm.cmd ci
    } else {
        Write-Step "npm install"
        & npm.cmd install
    }
    if ($LASTEXITCODE -ne 0) { Fail "npm failed to install the frontend dependencies." }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Frontend dependencies installed. Start it with scripts\start-frontend.ps1 (http://127.0.0.1:5173)." -ForegroundColor Green
